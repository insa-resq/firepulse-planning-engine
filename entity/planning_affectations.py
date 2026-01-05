from ortools.sat.python import cp_model
from typing import Dict, List, Tuple
from entity.casernefactory import CaserneFactory
from entity.caserne import Caserne
from entity.vehicule import *
from entity.pompier import Qualification
import itertools


class PlanningAvecAffectations:
    """
    NOUVELLE VERSION avec affectation précise des pompiers aux postes.
    Cette version garantit que chaque poste de chaque véhicule a exactement un pompier,
    et qu'un pompier ne peut occuper qu'un seul poste par jour.
    """

    def __init__(self):
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()

    def definir_probleme(self, caserne: Caserne, jours: List[int]):
        """Initialise le problème avec une caserne et les jours de la semaine."""
        self.caserne = caserne
        self.pompiers = caserne.pompiers
        self.vehicules = caserne.vehicules
        self.jours = jours

        # Paramètres de base
        self.params = {
            "MAX_JOURS_SEMAINE": 5,
            "MAX_CONSECUTIFS": 3,
            "MIN_POMPIERS_PAR_JOUR": 10
        }

        print(f"\n📊 CASERNE : {len(self.pompiers)} pompiers, {len(self.vehicules)} véhicules")
        print(f"📅 JOURS : {len(self.jours)} jours (du lundi au dimanche)")

        # Afficher les véhicules
        print("\n🚒 VÉHICULES :")
        for i, v in enumerate(self.vehicules):
            conditions = v.get_conditions()
            print(f"  {v.__class__.__name__} (ID:{i}) : {v.taille_equipe} postes")
            for qualif, nb in conditions.items():
                print(f"    - {qualif.name}: {nb} poste(s)")

    def peut_occuper_poste(self, pompier, qualif_requise):
        """
        Vérifie si un pompier peut occuper un poste nécessitant une qualification.
        Prend en compte la hiérarchie des chefs.
        """
        # Si le pompier a la qualification exacte
        if pompier.a_qualification(qualif_requise):
            return True

        # Hiérarchie des chefs
        if qualif_requise == Qualification.CHEF_PE:
            # CHEF_PE peut être remplacé par CHEF_ME ou CHEF_GE
            return (pompier.a_qualification(Qualification.CHEF_ME) or
                    pompier.a_qualification(Qualification.CHEF_GE))
        elif qualif_requise == Qualification.CHEF_ME:
            # CHEF_ME peut être remplacé par CHEF_GE
            return pompier.a_qualification(Qualification.CHEF_GE)

        # Pour les autres qualifications, pas de substitution possible
        return False

    def creer_variables(self):
        """
        Crée TOUTES les variables nécessaires :
        - Y : affectations pompiers → postes
        - X : présence des pompiers (dérivée des affectations)
        """
        print("\n🔧 Création des variables...")

        self.Y = {}  # Variables d'affectation
        self.X = {}  # Variables de présence

        # 1. Créer les variables d'affectation (Y)
        total_variables = 0
        for j in self.jours:
            for v_idx, vehicule in enumerate(self.vehicules):
                # Obtenir les postes nécessaires pour ce véhicule
                conditions = vehicule.get_conditions()
                postes = []
                for qualif, nombre in conditions.items():
                    for i in range(nombre):
                        postes.append((qualif, i))  # (qualification, numéro)

                # Pour chaque poste
                for poste_idx, (qualif_requise, _) in enumerate(postes):
                    # Pour chaque pompier
                    for p in self.pompiers:
                        # Vérifier si le pompier peut occuper ce poste
                        if self.peut_occuper_poste(p, qualif_requise):
                            # Créer la variable d'affectation
                            var_name = f"Y_p{p.pompier_id}_v{v_idx}_p{poste_idx}_j{j}"
                            self.Y[(p, v_idx, poste_idx, j)] = self.model.NewBoolVar(var_name)
                            total_variables += 1

            # 2. Créer les variables de présence (X)
            for p in self.pompiers:
                var_name = f"X_p{p.pompier_id}_j{j}"
                self.X[(p, j)] = self.model.NewBoolVar(var_name)

        print(f"✅ Variables créées : {total_variables} variables d'affectation")

    def ajouter_contrainte_ecart_jours(self):
        """
        Contrainte SOFT : minimiser l'écart entre les jours
        pour éviter les jours avec trop de postes vacants.
        """
        print("  - Équilibrer les postes entre les jours (SOFT)...")

        # Nombre total de postes par jour
        total_postes_jour = sum(v.taille_equipe for v in self.vehicules)

        # Variables pour les postes pourvus chaque jour
        # postes_pourvus[j] = total_postes - manques[j]
        self.postes_pourvus_par_jour = []

        for j in self.jours:
            pourvus = self.model.NewIntVar(0, total_postes_jour, f"pourvus_j{j}")
            self.model.Add(pourvus == total_postes_jour - self.manques_total_jour[j])
            self.postes_pourvus_par_jour.append(pourvus)

        # Variables pour le minimum et maximum de postes pourvus
        self.min_pourvus = self.model.NewIntVar(0, total_postes_jour, "min_pourvus")
        self.max_pourvus = self.model.NewIntVar(0, total_postes_jour, "max_pourvus")

        # Contraintes : min <= chaque jour <= max
        for j in self.jours:
            self.model.Add(self.min_pourvus <= self.postes_pourvus_par_jour[j])
            self.model.Add(self.postes_pourvus_par_jour[j] <= self.max_pourvus)

        # Différence entre max et min (à minimiser)
        self.ecart_max_min = self.model.NewIntVar(0, total_postes_jour, "ecart_max_min")
        self.model.Add(self.ecart_max_min == self.max_pourvus - self.min_pourvus)

        return self.ecart_max_min



    def ajouter_contraintes(self):
        """Ajoute TOUTES les contraintes au modèle."""
        print("\n🔗 Ajout des contraintes...")

        # VARIABLES POUR LE MANQUE DE PERSONNEL (SOFT)
        self.manques_poste = {}  # Manque par poste
        self.manques_total_jour = []  # Manque total par jour

        # 1. CONTRAINTE SOFT : Chaque poste devrait avoir un pompier
        print("  - Chaque poste devrait avoir un pompier (SOFT)...")

        for j in self.jours:
            manque_total_jour = self.model.NewIntVar(0, 100, f"manque_total_j{j}")
            self.manques_total_jour.append(manque_total_jour)

            manques_jour = []

            for v_idx, vehicule in enumerate(self.vehicules):
                conditions = vehicule.get_conditions()
                postes = []
                for qualif, nombre in conditions.items():
                    for i in range(nombre):
                        postes.append((qualif, i))

                for poste_idx, _ in enumerate(postes):
                    # Récupérer toutes les variables pour ce poste
                    variables_poste = []
                    for p in self.pompiers:
                        key = (p, v_idx, poste_idx, j)
                        if key in self.Y:
                            variables_poste.append(self.Y[key])

                    if variables_poste:
                        # Variable de manque pour ce poste (0 si occupé, 1 si vide)
                        manque_poste = self.model.NewBoolVar(f"manque_v{v_idx}_p{poste_idx}_j{j}")
                        self.manques_poste[(v_idx, poste_idx, j)] = manque_poste

                        # Contrainte SOFT : sum(variables) + manque_poste == 1
                        # Si sum=1 → manque=0 (poste occupé)
                        # Si sum=0 → manque=1 (poste vacant)
                        self.model.Add(sum(variables_poste) + manque_poste == 1)

                        manques_jour.append(manque_poste)

            # Le manque total du jour = somme des manques par poste
            if manques_jour:
                self.model.Add(manque_total_jour == sum(manques_jour))
            else:
                self.model.Add(manque_total_jour == 0)

        # 2. CONTRAINTE HARD : Un pompier ne peut occuper qu'un poste par jour
        print("  - Un pompier ne peut occuper qu'un poste par jour (HARD)...")
        for j in self.jours:
            for p in self.pompiers:
                affectations_du_jour = []
                for (p2, v_idx, poste_idx, j2), var in self.Y.items():
                    if p2 == p and j2 == j:
                        affectations_du_jour.append(var)

                if affectations_du_jour:
                    # Contrainte HARD : au plus une affectation
                    self.model.Add(sum(affectations_du_jour) <= 1)

        # 3. CONTRAINTE HARD : Lien entre affectations et présence
        print("  - Lien entre affectations et présence (HARD)...")
        for j in self.jours:
            for p in self.pompiers:
                # Récupérer toutes les affectations de ce pompier ce jour
                affectations = []
                for (p2, v_idx, poste_idx, j2), var in self.Y.items():
                    if p2 == p and j2 == j:
                        affectations.append(var)

                if affectations:
                    # X[p,j] == sum(affectations) (car sum <= 1)
                    self.model.Add(self.X[(p, j)] == sum(affectations))
                else:
                    self.model.Add(self.X[(p, j)] == 0)

        # 4. CONTRAINTES HARD EXISTANTES
        print("  - Contraintes de base du planning (HARD)...")

        # Max 5 jours par semaine (HARD)
        for p in self.pompiers:
            jours_travailles = [self.X[(p, j)] for j in self.jours]
            self.model.Add(sum(jours_travailles) <= self.params["MAX_JOURS_SEMAINE"])

        # Max 3 jours consécutifs (HARD)
        for p in self.pompiers:
            for j in range(len(self.jours) - 2):
                self.model.Add(
                    self.X[(p, j)] + self.X[(p, j + 1)] + self.X[(p, j + 2)]
                    <= self.params["MAX_CONSECUTIFS"]
                )

        # Minimum de pompiers par jour (HARD)
        for j in self.jours:
            pompiers_presents = [self.X[(p, j)] for p in self.pompiers]
            self.model.Add(sum(pompiers_presents) >= self.params["MIN_POMPIERS_PAR_JOUR"])

        print("✅ Toutes les contraintes sont ajoutées")

    def ajouter_objectif(self):
        """Définit l'objectif à optimiser avec équilibre entre jours."""
        print("\n🎯 Définition de l'objectif...")

        # 1. OBJECTIF : Minimiser les postes vacants sur la semaine (PRIORITAIRE)
        total_manques_semaine = sum(self.manques_total_jour)

        # 2. OBJECTIF : Minimiser l'écart entre les jours (pour éviter Samedi=50%, Dimanche=96%)
        ecart_jours = self.ajouter_contrainte_ecart_jours()

        # 3. OBJECTIF : Équilibrer les jours de travail entre pompiers (secondaire)
        totaux_jours = []
        for p in self.pompiers:
            total = self.model.NewIntVar(0, 7, f"total_p{p.pompier_id}")
            self.model.Add(total == sum(self.X[(p, j)] for j in self.jours))
            totaux_jours.append(total)

        # Cible : 4 jours par pompier
        moyenne_cible = 4

        # Calcul des écarts
        ecarts = []
        for total in totaux_jours:
            ecart = self.model.NewIntVar(0, 7, "ecart_pompier")
            self.model.Add(ecart >= total - moyenne_cible)
            self.model.Add(ecart >= moyenne_cible - total)
            ecarts.append(ecart)

        somme_ecarts = sum(ecarts)

        # PONDÉRATION INTELLIGENTE
        # Priorités :
        # 1. Remplir les postes (le plus important)
        # 2. Équilibrer entre les jours (éviter les variations)
        # 3. Équilibrer entre pompiers (le moins important)

        COEFF_MANQUES = 10000  # Priorité 1 : postes vacants
        COEFF_ECART_JOURS = 100  # Priorité 2 : équilibre entre jours
        COEFF_EQUITE = 1  # Priorité 3 : équité pompiers

        # Objectif final combiné
        self.model.Minimize(
            COEFF_MANQUES * total_manques_semaine +
            COEFF_ECART_JOURS * ecart_jours +
            COEFF_EQUITE * somme_ecarts
        )

        print(f"✅ Objectif avec 3 composantes :")
        print(f"   1. Postes vacants (coeff {COEFF_MANQUES})")
        print(f"   2. Écart entre jours (coeff {COEFF_ECART_JOURS})")
        print(f"   3. Équité pompiers (coeff {COEFF_EQUITE})")

        # Sauvegarder pour l'affichage
        self.total_manques_semaine = total_manques_semaine
        self.ecart_jours = ecart_jours
        self.somme_ecarts = somme_ecarts

    def resoudre(self):
        """Résout le problème et affiche les résultats."""
        print("\n⚡ Résolution en cours...")

        # Paramètres pour accélérer la résolution
        self.solver.parameters.max_time_in_seconds = 30.0
        self.solver.parameters.num_search_workers = 8

        # Résoudre !
        status = self.solver.Solve(self.model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"\n✅ SOLUTION TROUVÉE !")
            print(f"   Score total : {self.solver.ObjectiveValue()}")

            # Afficher les composantes détaillées
            if hasattr(self, 'total_manques_semaine'):
                manques = self.solver.Value(self.total_manques_semaine)
                total_postes = sum(v.taille_equipe for v in self.vehicules) * 7
                taux_remplissage = ((total_postes - manques) / total_postes * 100) if total_postes > 0 else 0
                print(f"   Postes vacants sur la semaine : {manques}/{total_postes}")
                print(f"   Taux de remplissage : {taux_remplissage:.1f}%")

            if hasattr(self, 'ecart_jours'):
                ecart = self.solver.Value(self.ecart_jours)
                print(f"   Écart max-min entre jours : {ecart} postes")

            if hasattr(self, 'somme_ecarts'):
                ecarts = self.solver.Value(self.somme_ecarts)
                print(f"   Inéquité entre pompiers : {ecarts}")

            print(f"   Temps : {self.solver.WallTime():.2f} secondes")
            return True
        else:
            print(f"\n❌ Aucune solution trouvée")
            print(f"   Statut : {self.solver.StatusName(status)}")
            return False



    def afficher_resultats(self):
        """Affiche les résultats de façon lisible avec qualifications détaillées."""
        jours_noms = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

        print("\n" + "=" * 80)
        print("📊 PLANNING HEBDOMADAIRE DÉTAILLÉ")
        print("=" * 80)

        # STATISTIQUES GLOBALES DES QUALIFICATIONS
        print("\n🧮 STATISTIQUES GLOBALES DES QUALIFICATIONS :")
        print("-" * 50)

        # Compter les qualifications disponibles dans la caserne
        qualifs_disponibles = {}
        for qualif in Qualification:
            count = sum(1 for p in self.pompiers if p.a_qualification(qualif))
            qualifs_disponibles[qualif] = count

        # Compter les besoins totaux par qualification
        besoins_totaux = {}
        for v in self.vehicules:
            conditions = v.get_conditions()
            for qualif, nb in conditions.items():
                besoins_totaux[qualif] = besoins_totaux.get(qualif, 0) + nb

        print(f"{'Qualification':20} {'Disponible':12} {'Besoin/jour':12} {'Ratio':10}")
        print("-" * 50)
        for qualif in sorted(Qualification, key=lambda q: q.name):
            dispo = qualifs_disponibles.get(qualif, 0)
            besoin = besoins_totaux.get(qualif, 0)
            ratio = f"{dispo / besoin:.1%}" if besoin > 0 else "N/A"
            statut = "✓" if dispo >= besoin else "⚠"
            print(f"{statut} {qualif.name:18} {dispo:12} {besoin:12} {ratio:10}")

        # Pour chaque jour
        for j in self.jours:
            print(f"\n" + "=" * 80)
            print(f"📅 {jours_noms[j].upper()}")
            print("=" * 80)

            # Compter les présences
            pompiers_presents = [p for p in self.pompiers if self.solver.Value(self.X[(p, j)]) == 1]
            print(f"\n👨‍🚒 POMPIERS PRÉSENTS ({len(pompiers_presents)}/{len(self.pompiers)}) :")

            # Afficher les pompiers présents avec leurs qualifications
            for p in pompiers_presents:
                qualifs = [q.name for q in Qualification if p.a_qualification(q)]
                print(f"  - {p.prenom} {p.nom}: {', '.join(qualifs[:3])}" +
                      ("..." if len(qualifs) > 3 else ""))

            # ANALYSE DES QUALIFICATIONS DISPONIBLES CE JOUR
            print(f"\n🎯 QUALIFICATIONS DISPONIBLES CE JOUR :")
            print("-" * 50)

            qualifs_presentes = {}
            for qualif in Qualification:
                count = sum(1 for p in pompiers_presents if p.a_qualification(qualif))
                qualifs_presentes[qualif] = count

            print(f"{'Qualification':20} {'Présents':10} {'Besoin':10} {'Statut':10}")
            print("-" * 50)

            vehicules_complets = 0
            total_vehicules = len(self.vehicules)

            for qualif in sorted(Qualification, key=lambda q: q.name):
                if qualif in besoins_totaux:
                    presents = qualifs_presentes.get(qualif, 0)
                    besoin = besoins_totaux[qualif]
                    statut = "✓ SUFFISANT" if presents >= besoin else f"⚠ MANQUE {besoin - presents}"
                    print(f"{qualif.name:20} {presents:10} {besoin:10} {statut:10}")

            # AFFECTATIONS PAR VÉHICULE
            print(f"\n🚒 AFFECTATIONS DES VÉHICULES :")
            print("-" * 50)

            for v_idx, vehicule in enumerate(self.vehicules):
                type_vehicule = vehicule.__class__.__name__

                # Vérifier si le véhicule est complètement armé
                conditions = vehicule.get_conditions()
                postes_assignes = 0
                postes_totaux = vehicule.taille_equipe

                print(f"\n  {type_vehicule} (ID:{v_idx}) - {postes_totaux} postes :")

                postes = []
                for qualif, nombre in conditions.items():
                    for i in range(nombre):
                        postes.append((qualif, i))

                # Pour chaque poste
                for poste_idx, (qualif_requise, _) in enumerate(postes):
                    # Chercher le pompier affecté
                    pompier_trouve = None
                    for p in self.pompiers:
                        key = (p, v_idx, poste_idx, j)
                        if key in self.Y and self.solver.Value(self.Y[key]) == 1:
                            pompier_trouve = p
                            postes_assignes += 1
                            break

                    if pompier_trouve:
                        # Vérifier si le pompier a la qualification exacte ou supérieure
                        qualif_exacte = pompier_trouve.a_qualification(qualif_requise)
                        qualif_sup = False

                        # Vérifier les qualifications supérieures
                        if qualif_requise == Qualification.CHEF_PE:
                            qualif_sup = (pompier_trouve.a_qualification(Qualification.CHEF_ME) or
                                          pompier_trouve.a_qualification(Qualification.CHEF_GE))
                        elif qualif_requise == Qualification.CHEF_ME:
                            qualif_sup = pompier_trouve.a_qualification(Qualification.CHEF_GE)

                        qualif_info = ""
                        if qualif_exacte:
                            qualif_info = "✓ qualification exacte"
                        elif qualif_sup:
                            qualif_info = "↑ qualification supérieure"
                        else:
                            qualif_info = "? problème de qualification"

                        print(f"    ✓ Poste {poste_idx} ({qualif_requise.name}): "
                              f"{pompier_trouve.prenom} {pompier_trouve.nom} {qualif_info}")
                    else:
                        print(f"    ✗ Poste {poste_idx} ({qualif_requise.name}): VACANT")

                # Résumé du véhicule
                if postes_assignes == postes_totaux:
                    print(f"    ✅ Véhicule COMPLÈTEMENT armé ({postes_assignes}/{postes_totaux})")
                    vehicules_complets += 1
                else:
                    print(f"    ⚠ Véhicule INCOMPLET ({postes_assignes}/{postes_totaux})")

            # RÉSUMÉ DU JOUR
            print(f"\n📈 RÉSUMÉ DU {jours_noms[j].upper()} :")
            print(f"  - Pompiers présents : {len(pompiers_presents)}/{len(self.pompiers)}")
            print(f"  - Véhicules complets : {vehicules_complets}/{total_vehicules}")

            # Calcul du taux d'armement
            postes_totaux_jour = sum(v.taille_equipe for v in self.vehicules)
            postes_pourvus = 0
            for v_idx, vehicule in enumerate(self.vehicules):
                conditions = vehicule.get_conditions()
                for qualif, nombre in conditions.items():
                    for i in range(nombre):
                        poste_idx = len([p for p in postes if p[0] == qualif and p[1] < i])
                        for p in self.pompiers:
                            key = (p, v_idx, poste_idx, j)
                            if key in self.Y and self.solver.Value(self.Y[key]) == 1:
                                postes_pourvus += 1
                                break

            taux_armement = (postes_pourvus / postes_totaux_jour * 100) if postes_totaux_jour > 0 else 0
            print(f"  - Postes pourvus : {postes_pourvus}/{postes_totaux_jour} ({taux_armement:.1f}%)")

        # STATISTIQUES FINALES
        print("\n" + "=" * 80)
        print("🏆 STATISTIQUES FINALES DE LA SEMAINE")
        print("=" * 80)

        # Jours travaillés par pompier
        print("\n📅 JOURS TRAVAILLÉS PAR POMPIER :")
        print("-" * 40)

        stats_jours = {}
        jours_travail_totaux = []

        for p in self.pompiers:
            total = sum(self.solver.Value(self.X[(p, j)]) for j in self.jours)
            jours_travail_totaux.append(total)
            stats_jours[total] = stats_jours.get(total, 0) + 1

        # Afficher par ordre croissant de jours
        pompiers_tries = sorted(self.pompiers,
                                key=lambda p: sum(self.solver.Value(self.X[(p, j)]) for j in self.jours))

        for p in pompiers_tries:
            total = sum(self.solver.Value(self.X[(p, j)]) for j in self.jours)
            qualifs = [q.name for q in Qualification if p.a_qualification(q)]
            print(f"  {p.prenom:8} {p.nom:10} : {total} jour(s) - {', '.join(qualifs[:2])}")

        # Distribution
        print(f"\n📊 DISTRIBUTION DES JOURS DE TRAVAIL :")
        for jours in sorted(stats_jours.keys()):
            nb_pompiers = stats_jours[jours]
            pourcentage = (nb_pompiers / len(self.pompiers)) * 100
            print(f"  {jours} jour(s) : {nb_pompiers} pompier(s) ({pourcentage:.1f}%)")

        # Moyenne et équité
        moyenne = sum(jours_travail_totaux) / len(jours_travail_totaux)
        variance = sum((jours - moyenne) ** 2 for jours in jours_travail_totaux) / len(jours_travail_totaux)
        ecart_type = variance ** 0.5

        print(f"\n📈 INDICATEURS D'ÉQUITÉ :")
        print(f"  - Moyenne : {moyenne:.2f} jours/pompier")
        print(f"  - Écart-type : {ecart_type:.2f} (plus c'est bas, plus c'est équitable)")
        print(f"  - Min : {min(jours_travail_totaux)} jours")
        print(f"  - Max : {max(jours_travail_totaux)} jours")

        # Vérification globale
        print(f"\n✅ VÉRIFICATION GLOBALE :")
        print(f"  - Total pompiers : {len(self.pompiers)}")
        print(f"  - Total véhicules : {len(self.vehicules)}")
        print(f"  - Postes totaux/jour : {sum(v.taille_equipe for v in self.vehicules)}")
        print(f"  - Postes totaux/semaine : {sum(v.taille_equipe for v in self.vehicules) * 7}")

    def afficher_resultats_simple(self):
        """Affiche les résultats de façon simple et claire."""
        jours_noms = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

        print("\n" + "=" * 80)
        print("📊 RÉSULTATS DU PLANNING")
        print("=" * 80)

        # ============================================
        # 1. OBJECTIF : REMPLISSAGE DES POSTES
        # ============================================
        print("\n🎯 OBJECTIF 1 : REMPLISSAGE DES POSTES")
        print("-" * 40)

        total_postes_jour = sum(v.taille_equipe for v in self.vehicules)
        total_postes_semaine = total_postes_jour * 7

        postes_pourvus_semaine = 0
        stats_jours = []

        print(f"{'Jour':10} {'Pourvus':8} {'Total':8} {'Taux':10} {'Statut':12}")
        print("-" * 50)

        for j in self.jours:
            postes_vacants = self.solver.Value(self.manques_total_jour[j])
            postes_pourvus = total_postes_jour - postes_vacants
            postes_pourvus_semaine += postes_pourvus
            taux = (postes_pourvus / total_postes_jour * 100) if total_postes_jour > 0 else 0

            stats_jours.append(postes_pourvus)

            # Évaluation
            if taux >= 90:
                statut = "✅ EXCELLENT"
            elif taux >= 80:
                statut = "✅ BON"
            elif taux >= 70:
                statut = "⚠️  MOYEN"
            else:
                statut = "❌ FAIBLE"

            print(f"{jours_noms[j]:10} {postes_pourvus:3}/{total_postes_jour:<4} {taux:8.1f}%  {statut:12}")

        # Résumé de l'objectif 1
        taux_global = (postes_pourvus_semaine / total_postes_semaine * 100) if total_postes_semaine > 0 else 0

        print(f"\n📈 RÉSUMÉ POSTES :")
        print(f"  - Total postes pourvus : {postes_pourvus_semaine}/{total_postes_semaine}")
        print(f"  - Taux global : {taux_global:.1f}%")

        # Écart entre jours (objectif 2)
        min_jour = min(stats_jours)
        max_jour = max(stats_jours)
        ecart = max_jour - min_jour

        # ============================================
        # 2. OBJECTIF : ÉQUILIBRE ENTRE JOURS
        # ============================================
        print(f"\n🎯 OBJECTIF 2 : ÉQUILIBRE ENTRE JOURS")
        print("-" * 40)

        print(f"  - Meilleur jour : {max_jour}/{total_postes_jour} ({max_jour / total_postes_jour * 100:.1f}%)")
        print(f"  - Pire jour : {min_jour}/{total_postes_jour} ({min_jour / total_postes_jour * 100:.1f}%)")
        print(f"  - Écart : {ecart} postes")

        # Évaluation de l'équilibre
        if ecart <= 2:
            evaluation = "✅ EXCELLENT (très équilibré)"
        elif ecart <= 5:
            evaluation = "✅ BON (assez équilibré)"
        elif ecart <= 10:
            evaluation = "⚠️  MOYEN (variations modérées)"
        else:
            evaluation = "❌ FAIBLE (fortes variations)"

        print(f"  - Évaluation : {evaluation}")

        # ============================================
        # 3. OBJECTIF : ÉQUITÉ ENTRE POMPIERS
        # ============================================
        print(f"\n🎯 OBJECTIF 3 : ÉQUITÉ ENTRE POMPIERS")
        print("-" * 40)

        jours_par_pompier = []
        for p in self.pompiers:
            total = sum(self.solver.Value(self.X[(p, j)]) for j in self.jours)
            jours_par_pompier.append(total)

        min_jours = min(jours_par_pompier)
        max_jours = max(jours_par_pompier)
        moyenne_jours = sum(jours_par_pompier) / len(jours_par_pompier)
        ecart_jours = max_jours - min_jours

        print(f"  - Moyenne : {moyenne_jours:.1f} jours/pompier")
        print(f"  - Min : {min_jours} jours")
        print(f"  - Max : {max_jours} jours")
        print(f"  - Écart : {ecart_jours} jours")

        # Distribution
        print(f"\n  Distribution :")
        distribution = {}
        for jours in jours_par_pompier:
            distribution[jours] = distribution.get(jours, 0) + 1

        for jours in sorted(distribution.keys()):
            nb = distribution[jours]
            pourcentage = (nb / len(self.pompiers)) * 100
            barre = "█" * int(pourcentage / 5)  # Barre de progression
            print(f"    {jours} jours : {nb:3} pompiers {barre}")

        # Évaluation de l'équité
        if ecart_jours <= 1:
            evaluation = "✅ EXCELLENT (très équitable)"
        elif ecart_jours <= 2:
            evaluation = "✅ BON (assez équitable)"
        elif ecart_jours <= 3:
            evaluation = "⚠️  MOYEN (inégalités modérées)"
        else:
            evaluation = "❌ FAIBLE (fortes inégalités)"

        print(f"  - Évaluation : {evaluation}")

        # ============================================
        # 4. RÉSUMÉ GLOBAL
        # ============================================
        print(f"\n" + "=" * 80)
        print("🏆 BILAN GLOBAL")
        print("=" * 80)

        print(f"\n📊 INDICATEURS CLÉS :")
        print(f"  1. Remplissage postes : {taux_global:5.1f}%")
        print(f"  2. Écart entre jours : {ecart:5} postes")
        print(f"  3. Écart pompiers : {ecart_jours:5} jours")

        # Score global (simplifié)
        score_remplissage = min(100, taux_global)
        score_equilibre = max(0, 100 - ecart * 2)  # Pénalité de 2% par poste d'écart
        score_equite = max(0, 100 - ecart_jours * 10)  # Pénalité de 10% par jour d'écart

        score_global = (score_remplissage * 0.5 +  # Poids 50% pour le remplissage
                        score_equilibre * 0.3 +  # Poids 30% pour l'équilibre
                        score_equite * 0.2)  # Poids 20% pour l'équité

        print(f"\n⭐ SCORE GLOBAL : {score_global:.1f}/100")

        # Note globale
        if score_global >= 90:
            note = "A - EXCELLENT"
        elif score_global >= 80:
            note = "B - TRÈS BON"
        elif score_global >= 70:
            note = "C - SATISFAISANT"
        elif score_global >= 60:
            note = "D - PASSABLE"
        else:
            note = "E - INSUFFISANT"

        print(f"   📝 Note : {note}")

        # Recommandations
        print(f"\n💡 RECOMMANDATIONS :")
        if taux_global < 80:
            print(f"  • Augmenter le nombre de pompiers ou réduire les véhicules")
        if ecart > 5:
            print(f"  • Mieux répartir la charge entre les jours")
        if ecart_jours > 2:
            print(f"  • Améliorer l'équité entre les pompiers")

        # ============================================
        # 5. VÉHICULES LES PLUS PROBLÉMATIQUES
        # ============================================
        print(f"\n🔍 VÉHICULES À AMÉLIORER :")

        problemes_vehicules = []
        for v_idx, vehicule in enumerate(self.vehicules):
            type_vehicule = vehicule.__class__.__name__
            postes_vides = 0

            # Compter les postes vides sur la semaine
            for j in self.jours:
                conditions = vehicule.get_conditions()
                for qualif, nombre in conditions.items():
                    for i in range(nombre):
                        poste_idx = sum(1 for q2, n2 in conditions.items()
                                        if q2 == qualif and n2 <= i)
                        vacants_jour = 0
                        for p in self.pompiers:
                            key = (p, v_idx, poste_idx, j)
                            if key in self.Y and self.solver.Value(self.Y[key]) == 0:
                                vacants_jour += 1
                        if vacants_jour == len(self.pompiers):  # Personne ne peut occuper
                            postes_vides += 1

            if postes_vides > 0:
                taux_vide = (postes_vides / (vehicule.taille_equipe * 7)) * 100
                problemes_vehicules.append((type_vehicule, taux_vide, postes_vides))

        if problemes_vehicules:
            problemes_vehicules.sort(key=lambda x: x[1], reverse=True)
            for type_vehicule, taux_vide, nb_vides in problemes_vehicules[:3]:  # Top 3
                print(f"  • {type_vehicule} : {nb_vides} postes vacants ({taux_vide:.1f}%)")
        else:
            print(f"  ✅ Tous les véhicules sont bien armés")
    def sauvegarder_resultats(self, filename="planning_affectations.txt"):
        """Sauvegarde les résultats dans un fichier."""
        jours_noms = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

        with open(filename, 'w', encoding='utf-8') as f:
            f.write("PLANNING HEBDOMADAIRE - AFFECTATIONS DÉTAILLÉES\n")
            f.write("=" * 80 + "\n\n")

            # En-tête
            f.write(f"Caserne ID: {self.caserne.caserne_id}\n")
            f.write(f"Type de caserne: {self.caserne.type_caserne}\n")
            f.write(f"Pompiers: {len(self.pompiers)}\n")
            f.write(f"Véhicules: {len(self.vehicules)}\n\n")

            # Pour chaque jour
            for j in self.jours:
                f.write(f"\n" + "=" * 80 + "\n")
                f.write(f"{jours_noms[j].upper()}\n")
                f.write("=" * 80 + "\n\n")

                # Présences
                presents = [p for p in self.pompiers if self.solver.Value(self.X[(p, j)]) == 1]
                f.write(f"Pompiers présents ({len(presents)}/{len(self.pompiers)}) :\n")
                for p in presents:
                    f.write(f"  - {p.prenom} {p.nom}\n")
                f.write("\n")

                # Affectations par véhicule
                f.write("AFFECTATIONS DES VÉHICULES :\n")
                f.write("-" * 40 + "\n")

                for v_idx, vehicule in enumerate(self.vehicules):
                    type_vehicule = vehicule.__class__.__name__
                    f.write(f"\n{type_vehicule} :\n")

                    conditions = vehicule.get_conditions()
                    postes = []
                    for qualif, nombre in conditions.items():
                        for i in range(nombre):
                            postes.append((qualif, i))

                    for poste_idx, (qualif_requise, _) in enumerate(postes):
                        # Chercher le pompier
                        pompier_trouve = None
                        for p in self.pompiers:
                            key = (p, v_idx, poste_idx, j)
                            if key in self.Y and self.solver.Value(self.Y[key]) == 1:
                                pompier_trouve = p
                                break

                        if pompier_trouve:
                            f.write(f"  Poste {poste_idx} ({qualif_requise.name}): "
                                    f"{pompier_trouve.prenom} {pompier_trouve.nom}\n")
                        else:
                            f.write(f"  Poste {poste_idx} ({qualif_requise.name}): NON POURVU\n")

        print(f"\n💾 Planning sauvegardé dans : {filename}")


def main():
    """
    FONCTION PRINCIPALE
    Exécute le programme complet.
    """
    print("=" * 80)
    print("PLANNING DES POMPIERS - NOUVELLE VERSION AVEC AFFECTATIONS")
    print("=" * 80)

    # 1. Créer une caserne (commence avec peu de monde pour tester)
    print("\n1. Création de la caserne...")
    caserne = CaserneFactory.creer_caserne(
        nb_pompiers=32,  # Petit effectif pour tester
        station_id=1,
        type_caserne="urbaine"  # Type simple
    )

    # 2. Définir les jours (une semaine)
    jours = list(range(7))  # 0= Lundi, 6= Dimanche

    # 3. Créer le planificateur
    print("\n2. Initialisation du planificateur...")
    planning = PlanningAvecAffectations()
    planning.definir_probleme(caserne, jours)

    # 4. Créer les variables
    planning.creer_variables()

    # 5. Ajouter les contraintes
    planning.ajouter_contraintes()

    # 6. Ajouter l'objectif
    planning.ajouter_objectif()

    # 7. Résoudre
    if planning.resoudre():
        # 8. Afficher les résultats
        planning.afficher_resultats_simple()

        # 9. Sauvegarder
        planning.sauvegarder_resultats()
    else:
        print("\n❌ Impossible de trouver une solution. Essayez avec :")
        print("   - Plus de pompiers")
        print("   - Moins de véhicules")
        print("   - Des paramètres moins stricts")


if __name__ == "__main__":
    main()