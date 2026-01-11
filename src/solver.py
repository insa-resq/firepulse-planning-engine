import asyncio
import sys
from pathlib import Path
from typing import List, Tuple, Final, Optional

from ortools.sat.python import cp_model

from src.entities.firefighter import FirefighterFilters
from src.entities.firefighter_training import FirefighterTrainingFilters
from src.entities.pompier import Qualification, Pompier, Grade
from src.entities.vehicle import VehicleFilters
from src.entities.vehicule import Vehicule
from src.utils.remote_client import remote_client

_OUTPUT_DIR: Final = Path("output")

_MAX_WORKING_DAYS_PER_WEEK: Final = 5
_MAX_CONSECUTIVE_WORKING_DAYS: Final = 3
_MIN_FIREFIGHTERS_PER_DAY: Final = 10
_WEEK_DAYS: Final = list(range(7))

try:
    from codecarbon import track_emissions
    print("CodeCarbon is available. Tracking enabled.")
except ImportError:
    print("CodeCarbon not found. Tracking disabled.")

    def track_emissions(fn=None, **_):
        """
        A no-op decorator that does nothing but return the original function.
        It handles both @track_emissions and @track_emissions(param=...) usages.
        """
        # Case 1: Called as @track_emissions (no parentheses)
        if fn is not None and callable(fn):
            return fn

        # Case 2: Called as @track_emissions(...) (with parentheses/arguments)
        def decorator(func):
            return func
        return decorator

async def _get_pompiers_for_station(station_id: str) -> List[Pompier]:
    # 1. Récupérer les firefighters depuis l'API
    firefighters = await remote_client.get_firefighters(
        filters=FirefighterFilters(stationId=station_id)
    )

    pompiers = []

    for firefighter in firefighters:
        # 2. Récupérer les trainings pour ce firefighter
        firefighter_training = (
            await remote_client.get_firefighter_trainings(
                filters=FirefighterTrainingFilters(firefighterId=firefighter.id)
            )
        )[0]

        # 5. Créer l'objet Pompier
        pompier = Pompier(
            nom=firefighter.lastName,
            prenom=firefighter.firstName,
            station_id=firefighter.stationId,
            pompier_id=firefighter.id,
            grade=Grade.from_rank(firefighter.rank),
            qualifications=[
                firefighter_training.permitB,
                firefighter_training.permitC,
                firefighter_training.suap,
                firefighter_training.inc,
                firefighter_training.permitAircraft,
                firefighter_training.smallTeamLeader,
                firefighter_training.mediumTeamLeader,
                firefighter_training.largeTeamLeader
            ]
        )

        pompiers.append(pompier)

    return pompiers

async def _get_vehicules_for_station(station_id: str) -> List[Vehicule]:
    """
    Récupère tous les véhicules d'une station et les convertit en objets Vehicule
    """

    # 1. Récupérer les données brutes des types de véhicules
    vehicles = await remote_client.get_vehicles(
        filters=VehicleFilters(stationId=station_id)
    )

    vehicules = []

    # 2. Pour chaque type de véhicule
    for vehicle in vehicles:
        if vehicle.totalCount <= 0:
            continue

        # 3. Créer les instances selon totalCount
        for i in range(vehicle.totalCount):
            # Créer le véhicule selon le type
            vehicule = Vehicule.from_vehicle_type(vehicle.type)

            # Définir les attributs
            vehicule.vehicule_id = f"{vehicle.id}_{i + 1}"
            vehicule.caserne_id = station_id
            vehicule.disponible = (i < vehicle.availableCount)
            vehicule.type_name = vehicle.type
            vehicule.instance_num = i + 1

            vehicules.append(vehicule)

    return vehicules

# =====================================================
# 1) Données du problème
# =====================================================
async def _get_data(planning_id: str) -> Tuple[List[Pompier], List[Vehicule]]:
    planning = await remote_client.get_planning(planning_id=planning_id)
    fire_station = await remote_client.get_fire_station(station_id=planning.stationId)

    # Récupérer en parallèle les véhicules et pompiers
    vehicules, pompiers = await asyncio.gather(
        _get_vehicules_for_station(station_id=fire_station.id),
        _get_pompiers_for_station(station_id=fire_station.id)
    )

    return pompiers, vehicules


# =====================================================
# 2) Création des variables du modèle
# =====================================================

def _create_variables(model, pompiers):
    X = {}
    for p in pompiers:
        for j in _WEEK_DAYS:
            X[p, j] = model.NewBoolVar(
                f"travail_p{p.pompier_id}_j{j}"
            )
    return X


# =====================================================
# 3) Contraintes
# =====================================================

def add_contrainte_max_jours(model, X, pompiers):
    for p in pompiers:
        model.Add(sum(X[p, j] for j in _WEEK_DAYS) <= _MAX_WORKING_DAYS_PER_WEEK)


def add_contrainte_consecutifs(model, X, pompiers):
    for p in pompiers:
        for j in range(5):
            model.Add(
                X[p, j] + X[p, j + 1] + X[p, j + 2] <= _MAX_CONSECUTIVE_WORKING_DAYS
            )


def add_contrainte_presence_journaliere(model, X, pompiers):
    for j in _WEEK_DAYS:
        model.Add(
            sum(X[p, j] for p in pompiers) >= _MIN_FIREFIGHTERS_PER_DAY
        )


# =====================================================
# 4) Objectif (équilibrer les jours travaillés)
# =====================================================

def add_soft_contrainte_vehicules(model, X, pompiers, vehicules):
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

    for j in _WEEK_DAYS:
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


def add_objective_equilibre(model, X, pompiers, manques):
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
        model.Add(totaux[p] == sum(X[p, j] for j in _WEEK_DAYS))

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


def add_soft_contrainte_qualifications_avec_hierarchie(model, X, pompiers, vehicules):
    """
    Contrainte SOFT pour l'armement des véhicules avec hiérarchie des chefs.

    Hiérarchie : CHEF_GE > CHEF_ME > CHEF_PE
    Un chef de niveau supérieur peut remplir un rôle de niveau inférieur.
    """

    # 1. Calculer les besoins totaux en qualifications
    besoins_totaux = {}
    for vehicule in vehicules:
        for qualif, nombre in vehicule.conditions.items():
            besoins_totaux[qualif] = besoins_totaux.get(qualif, 0) + nombre

    # Hiérarchie des chefs
    HIERARCHIE_CHEFS = {
        Qualification.CHEF_PE: [Qualification.CHEF_PE],
        Qualification.CHEF_ME: [Qualification.CHEF_PE, Qualification.CHEF_ME],
        Qualification.CHEF_GE: [Qualification.CHEF_PE, Qualification.CHEF_ME, Qualification.CHEF_GE]
    }

    manques_jour = []

    for j in _WEEK_DAYS:
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

# =====================================================
# 5) Solve et affichage
# =====================================================

def add_objective_complet(model, X, pompiers, manques_vehicules, manques_qualifs):
    """
    Objectif complet avec les 3 contraintes soft.
    """
    # Calcul des écarts d'équité
    totaux = {
        p: model.NewIntVar(0, 7, f"total_p{p.pompier_id}")
        for p in pompiers
    }

    for p in pompiers:
        model.Add(totaux[p] == sum(X[p, j] for j in _WEEK_DAYS))

    moyenne = 5
    ecarts = []

    for p in pompiers:
        ecart = model.NewIntVar(0, 7, f"ecart_p{p.pompier_id}")
        model.Add(ecart >= totaux[p] - moyenne)
        model.Add(ecart >= moyenne - totaux[p])
        ecarts.append(ecart)

    model.Minimize(
        1000 * sum(manques_qualifs) +  # Priorité MAX : qualifications
        100 * sum(manques_vehicules) +  # Priorité haute : véhicules
        1 * sum(ecarts)  # Priorité basse : équité
    )


def run_solver(model, X, pompiers, vehicules, output_file=None):
    solver = cp_model.CpSolver()

    # Optionnel : paramètres pour accélérer la résolution
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    jours_noms = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

    # Calculer les statistiques
    stats = {
        "jours_travailles": {p: 0 for p in pompiers},
        "presents_par_jour": {j: 0 for j in _WEEK_DAYS},
        "manque_total": 0,
        "pourcentages_jour": {j: 0 for j in _WEEK_DAYS}
    }

    # Données par pompier
    textes_stats_pompiers = []
    for p in pompiers:
        ligne = f"{p.prenom + " " + p.nom:20} : "
        total = 0
        for j in _WEEK_DAYS:
            travaille = solver.Value(X[p, j])
            ligne += "⬜ " if travaille else "🟥 "
            total += travaille
            stats["presents_par_jour"][j] += travaille
        stats["jours_travailles"][p] = total
        textes_stats_pompiers.append(ligne + f" {total:3}")

    # Calcul du besoin total pour l'armement
    besoin_total = sum(v.taille_equipe for v in vehicules)

    # Calcul du pourcentage de couverture par jour
    pourcentages = []
    textes_pourcentages = []

    for j in _WEEK_DAYS:
        presents = stats["presents_par_jour"][j]
        manque = max(0, besoin_total - presents)
        stats["manque_total"] += manque
        pourcentage = (presents / besoin_total * 100) if besoin_total > 0 else 100
        stats["pourcentages_jour"][j] = pourcentage

        pourcentages.append(pourcentage)
        textes_pourcentages.append(f"{jours_noms[j]:10} {presents:10} {besoin_total:10} {manque:10} {pourcentage:8.1f}%")

    # CALCUL MOYENNE
    pourcentage_moyen = sum(pourcentages) / len(pourcentages) if pourcentages else 0

    if output_file is not None:
        with open(_OUTPUT_DIR / output_file, 'w', encoding='utf-8') as f:
            f.write("PLANNING HEBDOMADAIRE\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"Statut de la résolution: {solver.StatusName(status)}\n")
            f.write(f"Score optimal: {solver.ObjectiveValue()}\n\n")

            f.write("Répartition des pompiers par jour :\n")
            f.write("-" * 40 + "\n")

            # En-tête des jours
            f.write(f"{'Pompier':20}")
            for j in _WEEK_DAYS:
                f.write(f"{jours_noms[j]:4}")
            f.write(" Total\n")
            f.write("-" * 70 + "\n")

            for ligne in textes_stats_pompiers:
                f.write(ligne + "\n")

            f.write("\n" + "=" * 60 + "\n")
            f.write("STATISTIQUES\n")
            f.write("=" * 60 + "\n\n")

            # Statistiques par jour
            f.write("Présence quotidienne et armement des véhicules :\n")
            f.write("-" * 60 + "\n")
            f.write(f"{'Jour':10} {'Présents':10} {'Besoin':10} {'Manque':10} {'% couverture'}\n")
            f.write("-" * 60 + "\n")

            for j in _WEEK_DAYS:
                f.write(textes_pourcentages[j] + "\n")

            f.write(f"{'MOYENNE':10} {'':10} {'':10} {'':10} {pourcentage_moyen:8.1f}%\n")

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
    print(f"  - Pourcentage moyen de complétion : {pourcentage_moyen:.1f}%")

@track_emissions()
async def solve(planning_id: str, output_file: Optional[str] = None) -> None:
    try:
        firefighters, vehicles = await _get_data(planning_id)
    except Exception as e:
        print(f"Error fetching data for planning ID {planning_id}: {e}", file=sys.stderr)
        sys.exit(1)

    model = cp_model.CpModel()

    # ----------------------------
    # Variables
    # ----------------------------
    X = _create_variables(model, firefighters)

    # ----------------------------
    # Contraintes HARD
    # ----------------------------
    add_contrainte_max_jours(model, X, firefighters)

    add_contrainte_consecutifs(model, X, firefighters)

    add_contrainte_presence_journaliere(model, X, firefighters)

    # ----------------------------
    # Contrainte SOFT 1 : Véhicules
    # ----------------------------
    manques_vehicules = add_soft_contrainte_vehicules(model, X, firefighters, vehicles)

    # ----------------------------
    # Contrainte SOFT 2 : Qualifications
    # ----------------------------
    manques_qualifs, _ = add_soft_contrainte_qualifications_avec_hierarchie(model, X, firefighters, vehicles)

    # ----------------------------
    # Objectif global
    # ----------------------------
    add_objective_complet(model, X, firefighters, manques_vehicules, manques_qualifs)

    # ----------------------------
    # Résolution
    # ----------------------------
    run_solver(model, X, firefighters, vehicles, output_file)

if __name__ == "__main__":
    if len(sys.argv) == 2 or len(sys.argv) == 3:
        asyncio.run(
            solve(
                planning_id=sys.argv[1],
                output_file=sys.argv[2] if len(sys.argv) == 3 else None
            )
        )
    else:
        print(f"Invalid arguments. Usage: python -m src.solver <planning_id> [output_file]", file=sys.stderr)
