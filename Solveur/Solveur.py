from ortools.sat.python import cp_model
from entity.casernefactory import CaserneFactory
from entity.caserne import Caserne
from entity.pompier import Qualification


# =====================================================
# 1) Données du problème
# =====================================================

def get_data():
    # Création d'une caserne complète avec la nouvelle factory
    caserne = CaserneFactory.creer_caserne(
        nb_pompiers=50,
        station_id=1,
        type_caserne=None  # Type aléatoire selon les probabilités
    )

    # Afficher un résumé de la caserne créée
    print("\n" + "=" * 60)
    print("CASERNE CRÉÉE")
    print("=" * 60)
    caserne.resume()
    print("=" * 60 + "\n")

    pompiers = caserne.pompiers
    vehicules = caserne.vehicules
    jours = range(7)

    params = {
        "MAX_JOURS_SEMAINE": 5,
        "MAX_CONSECUTIFS": 3,
        "MIN_POMPIERS_PAR_JOUR": 10
    }

    return caserne, jours, params


# =====================================================
# 2) Création des variables du modèle
# =====================================================

def create_variables(model, pompiers, jours):
    X = {}
    for p in pompiers:
        for j in jours:
            X[p, j] = model.NewBoolVar(
                f"travail_p{p.pompier_id}_j{j}"
            )
    return X


# =====================================================
# 3) Contraintes
# =====================================================

def add_contrainte_max_jours(model, X, pompiers, jours, max_jours):
    for p in pompiers:
        model.Add(sum(X[p, j] for j in jours) <= max_jours)


def add_contrainte_consecutifs(model, X, pompiers, max_consecutifs):
    for p in pompiers:
        for j in range(5):
            model.Add(
                X[p, j] + X[p, j + 1] + X[p, j + 2] <= max_consecutifs
            )


def add_contrainte_presence_journaliere(model, X, pompiers, jours, minimum):
    for j in jours:
        model.Add(
            sum(X[p, j] for p in pompiers) >= minimum
        )


# =====================================================
# 4) Objectif (équilibrer les jours travaillés)
# =====================================================

def add_soft_contrainte_vehicules(model, X, pompiers, vehicules, jours):
    """
    Contrainte SOFT :
    On souhaite avoir chaque jour suffisamment de pompiers présents
    pour pouvoir armer tous les véhicules de la caserne en même temps.

    Si ce n'est pas possible, on autorise un manque (pénalité),
    que le solveur devra minimiser.
    """

    manques = []

    # Nombre total de pompiers nécessaires pour armer TOUS les véhicules
    # (somme des tailles d'équipe de chaque véhicule)
    besoin_total = sum(v.taille_equipe for v in vehicules)

    for j in jours:
        # Variable = nombre de pompiers présents le jour j
        presents = model.NewIntVar(
            0, len(pompiers), f"presents_j{j}"
        )
        model.Add(presents == sum(X[p, j] for p in pompiers))

        # Variable = manque de pompiers le jour j
        # (0 si on a assez de monde, >0 sinon)
        manque = model.NewIntVar(
            0, besoin_total, f"manque_j{j}"
        )

        # Contrainte souple :
        # présents + manque >= besoin total
        # => si présents < besoin, le manque absorbe la différence
        model.Add(presents + manque >= besoin_total)

        # On stocke le manque pour l'objectif global
        manques.append(manque)

    return manques


def add_objective_equilibre(model, X, pompiers, jours, manques):
    """
    Objectif du solveur :
    - Minimiser le manque de pompiers par jour (objectif principal)
    - Répartir équitablement les jours de travail entre les pompiers
    """

    # ----------------------------
    # Calcul du nombre de jours travaillés par pompier
    # ----------------------------

    totaux = {
        p: model.NewIntVar(0, 7, f"total_p{p.pompier_id}")
        for p in pompiers
    }

    for p in pompiers:
        # total_p = somme des jours où le pompier travaille
        model.Add(totaux[p] == sum(X[p, j] for j in jours))

    # Valeur cible moyenne (choisie à la main, entière)
    moyenne = 5  # cohérent avec MAX_JOURS_SEMAINE

    # ----------------------------
    # Calcul des écarts à la moyenne
    # ----------------------------

    ecarts = []

    for p in pompiers:
        # Écart = distance entre le nombre de jours travaillés
        # et la moyenne cible
        ecart = model.NewIntVar(0, 7, f"ecart_p{p.pompier_id}")

        model.Add(ecart >= totaux[p] - moyenne)
        model.Add(ecart >= moyenne - totaux[p])

        ecarts.append(ecart)

    # ----------------------------
    # Objectif global
    # ----------------------------

    # Pondération :
    # - le manque de pompiers est plus grave que l'inéquité
    # - le solveur privilégiera donc l'armement des véhicules
    model.Minimize(
        10 * sum(manques) + sum(ecarts)
    )


def add_soft_contrainte_qualifications_avec_hierarchie(model, X, pompiers, vehicules, jours):
    """
    Contrainte SOFT pour l'armement des véhicules avec hiérarchie des chefs.

    Hiérarchie : CHEF_GE > CHEF_ME > CHEF_PE
    Un chef de niveau supérieur peut remplir un rôle de niveau inférieur.
    """

    # 1. Calculer les besoins totaux en qualifications
    besoins_totaux = {}
    for vehicule in vehicules:
        conditions = vehicule.get_conditions()
        for qualif, nombre in conditions.items():
            besoins_totaux[qualif] = besoins_totaux.get(qualif, 0) + nombre

    # Hiérarchie des chefs
    HIERARCHIE_CHEFS = {
        Qualification.CHEF_PE: [Qualification.CHEF_PE],
        Qualification.CHEF_ME: [Qualification.CHEF_PE, Qualification.CHEF_ME],
        Qualification.CHEF_GE: [Qualification.CHEF_PE, Qualification.CHEF_ME, Qualification.CHEF_GE]
    }

    # print("\nBESOINS EN QUALIFICATIONS (avec hiérarchie des chefs) :")
    # for qualif, besoin in besoins_totaux.items():
    #     if qualif in HIERARCHIE_CHEFS:
    #         equivalents = [q.name for q in HIERARCHIE_CHEFS[qualif]]
    #         print(f"  {qualif.name}: {besoin} pompiers (peuvent être remplacés par: {', '.join(equivalents)})")
    #     else:
    #         print(f"  {qualif.name}: {besoin} pompiers")
    # print()

    manques_jour = []

    for j in jours:
        manque_total_jour = model.NewIntVar(0, 1000, f"manque_total_j{j}")
        manques_jour.append(manque_total_jour)

        # Variables pour chaque qualification ce jour
        manques_qualif_jour = []

        for qualif, besoin in besoins_totaux.items():
            # Pour les rôles de chef, considérer les équivalents hiérarchiques
            if qualif in HIERARCHIE_CHEFS:
                qualifications_valides = HIERARCHIE_CHEFS[qualif]
            else:
                qualifications_valides = [qualif]

            # Calculer le nombre total de pompiers avec une qualification valide
            disponibles = model.NewIntVar(0, len(pompiers), f"dispo_{qualif.name}_j{j}")

            # Créer une expression qui somme tous les pompiers avec une qualification valide
            expr = []
            for p in pompiers:
                # Vérifier si le pompier a AU MOINS une des qualifications valides
                for q_valide in qualifications_valides:
                    if p.a_qualification(q_valide):
                        expr.append(X[p, j])
                        break  # Un pompier ne compte qu'une fois même s'il a plusieurs qualifications valides

            if expr:
                model.Add(disponibles == sum(expr))
            else:
                model.Add(disponibles == 0)

            # Variable de manque
            manque_qualif = model.NewIntVar(0, besoin, f"manque_{qualif.name}_j{j}")

            # Contrainte avec substitution hiérarchique
            model.Add(disponibles + manque_qualif >= besoin)

            manques_qualif_jour.append(manque_qualif)

        model.Add(manque_total_jour == sum(manques_qualif_jour))

    return manques_jour, besoins_totaux


# Pour éviter qu'un pompier soit compté plusieurs fois pour le même poste,
# on peut ajouter une contrainte de non-duplication :

def add_contrainte_affectation_unique_par_qualification(model, X, pompiers, vehicules, jours):
    """
    Contrainte supplémentaire : un pompier ne peut occuper qu'un seul "poste"
    par qualification équivalente par jour.

    Par exemple, un CHEF_GE ne peut pas être compté comme CHEF_PE ET CHEF_ME ET CHEF_GE
    dans le même véhicule le même jour.
    """

    for j in jours:
        for p in pompiers:
            # Liste des qualifications que ce pompier peut remplacer
            qualifications_pompier = []

            # Pour chaque qualification, vérifier ce que le pompier peut faire
            for qualif in Qualification:
                if p.a_qualification(qualif):
                    if qualif == Qualification.CHEF_GE:
                        qualifications_pompier.extend(
                            [Qualification.CHEF_PE, Qualification.CHEF_ME, Qualification.CHEF_GE])
                    elif qualif == Qualification.CHEF_ME:
                        qualifications_pompier.extend([Qualification.CHEF_PE, Qualification.CHEF_ME])
                    elif qualif == Qualification.CHEF_PE:
                        qualifications_pompier.append(Qualification.CHEF_PE)
                    else:
                        qualifications_pompier.append(qualif)

            # Un pompier ne peut être utilisé qu'une fois par ensemble de qualifications équivalentes
            # On crée un indicateur pour chaque "groupe" de qualifications

            # Groupe 1 : Rôles de chef (mutuellement exclusifs)
            roles_chef = [Qualification.CHEF_PE, Qualification.CHEF_ME, Qualification.CHEF_GE]
            if any(p.a_qualification(q) for q in roles_chef):
                # Le pompier ne peut occuper qu'un seul rôle de chef par jour
                # Cette contrainte est déjà implicite car X[p,j] est binaire
                # Mais on peut ajouter une contrainte explicite si nécessaire
                pass

            # Pour d'autres qualifications qui pourraient se chevaucher
            # (ex: un pompier avec COND_B et COND_C ne peut conduire qu'un seul véhicule)
            # On pourrait ajouter des contraintes similaires si nécessaire


# =====================================================
# 5) Solve et affichage
# =====================================================

def solve_and_print(model, X, pompiers, vehicules, jours, output_file="planning.txt"):
    solver = cp_model.CpSolver()

    # Optionnel : paramètres pour accélérer la résolution
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    jours_noms = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

    # Calculer les statistiques
    stats = {
        "jours_travailles": {p: 0 for p in pompiers},
        "presents_par_jour": {j: 0 for j in jours},
        "manque_total": 0
    }

    # Calcul du besoin total pour l'armement
    besoin_total = sum(v.taille_equipe for v in vehicules)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("PLANNING HEBDOMADAIRE\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"Statut de la résolution: {solver.StatusName(status)}\n")
        f.write(f"Score optimal: {solver.ObjectiveValue()}\n\n")

        f.write("Répartition des pompiers par jour :\n")
        f.write("-" * 40 + "\n")

        # En-tête des jours
        f.write(f"{'Pompier':20}")
        for j in jours:
            f.write(f"{jours_noms[j]:4}")
        f.write(" Total\n")
        f.write("-" * 70 + "\n")

        # Données par pompier
        for p in pompiers:
            ligne = f"{p.prenom:8} {p.nom:10} : "
            total = 0
            for j in jours:
                travaille = solver.Value(X[p, j])
                ligne += "⬜ " if travaille else "🟥 "
                total += travaille
                stats["presents_par_jour"][j] += travaille
            stats["jours_travailles"][p] = total
            f.write(ligne + f" {total:3}\n")

        f.write("\n" + "=" * 60 + "\n")
        f.write("STATISTIQUES\n")
        f.write("=" * 60 + "\n\n")

        # Statistiques par jour
        f.write("Présence quotidienne et armement des véhicules :\n")
        f.write("-" * 60 + "\n")
        f.write(f"{'Jour':10} {'Présents':10} {'Besoin':10} {'Manque':10} {'% couverture'}\n")
        f.write("-" * 60 + "\n")

        for j in jours:
            presents = stats["presents_par_jour"][j]
            manque = max(0, besoin_total - presents)
            stats["manque_total"] += manque
            pourcentage = (presents / besoin_total * 100) if besoin_total > 0 else 100

            f.write(f"{jours_noms[j]:10} {presents:10} {besoin_total:10} {manque:10} {pourcentage:8.1f}%\n")

        f.write("\n" + "=" * 60 + "\n")
        f.write("RÉPARTITION DES JOURS DE TRAVAIL\n")
        f.write("=" * 60 + "\n\n")

        # Calcul de la distribution
        distribution = {i: 0 for i in range(8)}
        for p in pompiers:
            jours_p = stats["jours_travailles"][p]
            distribution[jours_p] = distribution.get(jours_p, 0) + 1

        f.write(f"{'Jours/semaine':15} {'Nb pompiers':12} {'%':10}\n")
        f.write("-" * 40 + "\n")

        total_pompiers = len(pompiers)
        for jours_semaine in sorted(distribution.keys()):
            nb = distribution[jours_semaine]
            pourcentage = (nb / total_pompiers * 100)
            f.write(f"{jours_semaine:15} {nb:12} {pourcentage:9.1f}%\n")

        # Informations sur les véhicules
        f.write("\n" + "=" * 60 + "\n")
        f.write("VÉHICULES DE LA CASERNE\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"Nombre total de véhicules: {len(vehicules)}\n")
        f.write(f"Besoin total en personnel pour armement: {besoin_total} pompiers\n\n")

        f.write("Détail par type de véhicule :\n")
        f.write("-" * 50 + "\n")

        compteur = {}
        for v in vehicules:
            type_name = v.__class__.__name__
            compteur[type_name] = compteur.get(type_name, 0) + 1

        for type_name, count in compteur.items():
            taille_equipe = vehicules[0].taille_equipe if any(
                isinstance(v, type(vehicules[0])) for v in vehicules) else 0
            f.write(f"{type_name:20} : {count:3} véhicule(s), taille équipe: {taille_equipe}\n")

    print(f"\n✅ Planning généré dans : {output_file}")
    print(f"📊 Statistiques sauvegardées dans le fichier")

    # Affichage rapide dans la console
    print(f"\nRésumé :")
    print(f"  - Pompiers présents en moyenne : {sum(stats['presents_par_jour'].values()) / 7:.1f}/jour")
    print(f"  - Manque total de personnel : {stats['manque_total']} jours-pompier")
    print(f"  - Besoin pour armement complet : {besoin_total} pompiers/jour")


# =====================================================
# 6) Pipeline principal
# =====================================================

def main():
    # ----------------------------
    # Données
    # ----------------------------
    caserne, jours, params = get_data()
    pompiers = caserne.pompiers
    vehicules = caserne.vehicules

    # ----------------------------
    # Modèle CP-SAT
    # ----------------------------
    model = cp_model.CpModel()

    # ----------------------------
    # Variables
    # ----------------------------
    X = create_variables(model, pompiers, jours)

    # ----------------------------
    # Contraintes HARD
    # ----------------------------
    add_contrainte_max_jours(
        model, X, pompiers, jours, params["MAX_JOURS_SEMAINE"]
    )

    add_contrainte_consecutifs(
        model, X, pompiers, params["MAX_CONSECUTIFS"]
    )

    add_contrainte_presence_journaliere(
        model, X, pompiers, jours, params["MIN_POMPIERS_PAR_JOUR"]
    )

    # ----------------------------
    # Contrainte SOFT (véhicules)
    # ----------------------------
    manques = add_soft_contrainte_vehicules(
        model, X, pompiers, vehicules, jours
    )

    # ----------------------------
    # Objectif global
    # ----------------------------
    add_objective_equilibre(
        model, X, pompiers, jours, manques
    )

    # ----------------------------
    # Résolution
    # ----------------------------
    solve_and_print(model, X, pompiers, vehicules, jours, "planning_detaille.txt")
    print(caserne.get_conditions())


if __name__ == "__main__":
    main()