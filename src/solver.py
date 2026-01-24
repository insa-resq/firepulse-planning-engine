import asyncio
import sys
from pathlib import Path
from typing import List, Tuple, Final, Optional

from ortools.sat.python import cp_model
import codecarbon
from src.entities.planning import PlanningFinalizationDto, VehicleAvailabilities
from src.entities.availability_slot_firefighter import AvailabilitySlotFF
from src.entities.firefighter import FirefighterFilters
from src.entities.firefighter_training import FirefighterTrainingFilters
from src.entities.pompier import Qualification, Pompier, Grade
from src.entities.shift_assignment import ShiftAssignmentCreationDto, ShiftType
from src.entities.vehicle import VehicleFilters
from src.entities.vehicule import Vehicule
from src.utils.remote_client import remote_client
from src.entities.availability_slot import Weekday, AvailabilitySlot, AvailabilitySlotFilters

# =====================================================
# CONSTANTES
# =====================================================
_OUTPUT_DIR: Final = Path("output")
_MAX_WORKING_DAYS_PER_WEEK: Final = 5
_MAX_CONSECUTIVE_WORKING_DAYS: Final = 3  # Vraiment 3 jours max d'affilée
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


# =====================================================
# RÉCUPÉRATION DES DONNÉES
# =====================================================

async def _get_pompiers_for_station(station_id: str) -> List[Pompier]:
    firefighters = await remote_client.get_firefighters(
        filters=FirefighterFilters(stationId=station_id)
    )

    pompiers = []
    for firefighter in firefighters:
        training = (await remote_client.get_firefighter_trainings(
            filters=FirefighterTrainingFilters(firefighterId=firefighter.id)
        ))[0]

        pompier = Pompier(
            nom=firefighter.lastName,
            prenom=firefighter.firstName,
            station_id=firefighter.stationId,
            pompier_id=firefighter.id,
            grade=Grade.from_rank(firefighter.rank),
            qualifications=[
                training.permitB, training.permitC, training.suap,
                training.inc, training.permitAircraft,
                training.smallTeamLeader, training.mediumTeamLeader,
                training.largeTeamLeader
            ]
        )
        pompiers.append(pompier)

    return pompiers

async def _get_availability_slot_for_firefighter_and_week(firefighter_id: str,week_number: int,year : int) -> List[AvailabilitySlotFF]:
    availability_slots = await remote_client.get_availability_slots(
        filters=AvailabilitySlotFilters(year=year, firefighterId=firefighter_id, weekNumber=week_number)
    )

    disponibilties = []
    for availability_slot in availability_slots:

        dispo = AvailabilitySlotFF(
            weekday=availability_slot.weekday,
            isAvailable=availability_slot.isAvailable,
            firefighterId=availability_slot.firefighterId,

        )
        disponibilties.append(dispo)

    return disponibilties

async def _get_vehicules_for_station(station_id: str) -> List[Vehicule]:
    vehicles = await remote_client.get_vehicles(
        filters=VehicleFilters(stationId=station_id)
    )

    vehicules = []
    for vehicle in vehicles:
        if vehicle.totalCount <= 0:
            continue

        for i in range(vehicle.totalCount):
            vehicule = Vehicule.from_vehicle_type(vehicle.type)
            vehicule.vehicule_id = f"{vehicle.id}_{i + 1}"
            vehicule.caserne_id = station_id
            vehicule.type_name = vehicle.type
            vehicule.instance_num = i + 1
            vehicules.append(vehicule)

    return vehicules


async def _get_availability_slots_for_all_firefighters(
        pompiers: List[Pompier],
        week_number: int,
        year: int
) -> dict[str, List[AvailabilitySlotFF]]:
    """
    Récupère les disponibilités de tous les pompiers pour une semaine donnée.

    Returns:
        dict[pompier_id, List[AvailabilitySlotFF]]
    """
    # Lancer toutes les requêtes en parallèle
    tasks = [
        _get_availability_slot_for_firefighter_and_week(
            firefighter_id=p.pompier_id,
            week_number=week_number,
            year=year
        )
        for p in pompiers
    ]

    all_slots = await asyncio.gather(*tasks)

    # Créer un dictionnaire pompier_id -> disponibilités
    availability_map = {}
    for pompier, slots in zip(pompiers, all_slots):
        availability_map[pompier.pompier_id] = slots

    return availability_map


async def _get_data(planning_id: str) -> Tuple[List[Pompier], List[Vehicule], dict, int, int]:
    """
    Récupère toutes les données nécessaires au planning.

    Returns:
        (pompiers, vehicules, availability_map, week_number, year)
    """
    planning = await remote_client.get_planning(planning_id=planning_id)
    fire_station = await remote_client.get_fire_station(station_id=planning.stationId)

    # Récupérer véhicules et pompiers en parallèle
    vehicules, pompiers = await asyncio.gather(
        _get_vehicules_for_station(station_id=fire_station.id),
        _get_pompiers_for_station(station_id=fire_station.id)
    )

    # Récupérer les disponibilités de tous les pompiers
    # ATTENTION: Vous devez récupérer week_number et year du planning !
    # Je suppose que planning a ces attributs, sinon adaptez
    week_number = planning.weekNumber  # À adapter selon votre modèle
    year = planning.year  # À adapter selon votre modèle

    availability_map = await _get_availability_slots_for_all_firefighters(
        pompiers=pompiers,
        week_number=week_number,
        year=year
    )

    return pompiers, vehicules, availability_map, week_number, year
# =====================================================
# CRÉATION DES VARIABLES
# =====================================================

def _create_variables(model, pompiers):
    """Variables X[p, j] : pompier p travaille le jour j"""
    X = {}
    for p in pompiers:
        for j in _WEEK_DAYS:
            X[p, j] = model.NewBoolVar(f"travail_p{p.pompier_id}_j{j}")
    return X


def create_role_assignments(model, pompiers, vehicules):
    """Variables Y[p, v_idx, r_idx, j] : pompier p a le rôle r du véhicule v le jour j

    Avec hiérarchie des chefs : CHEF_GE > CHEF_ME > CHEF_PE
    Un chef supérieur peut occuper un poste de chef inférieur
    """

    # Hiérarchie : un chef peut prendre un rôle de niveau inférieur
    HIERARCHIE_CHEFS = {
        Qualification.CHEF_GE: [Qualification.CHEF_GE, Qualification.CHEF_ME, Qualification.CHEF_PE],
        Qualification.CHEF_ME: [Qualification.CHEF_ME, Qualification.CHEF_PE],
        Qualification.CHEF_PE: [Qualification.CHEF_PE]
    }

    def peut_prendre_role(pompier, role):
        """Vérifie si un pompier peut prendre un rôle (avec hiérarchie)"""
        # Si le pompier a la qualification exacte
        if pompier.a_qualification(role):
            return True

        # Si c'est un rôle de chef, vérifier la hiérarchie
        if role in [Qualification.CHEF_PE, Qualification.CHEF_ME, Qualification.CHEF_GE]:
            # Chercher si le pompier a un grade supérieur
            for qual_superieure, quals_acceptees in HIERARCHIE_CHEFS.items():
                if role in quals_acceptees and pompier.a_qualification(qual_superieure):
                    return True

        return False

    Y = {}
    for p in pompiers:
        for v_idx, v in enumerate(vehicules):
            for r_idx, role in enumerate(v.roles):
                for j in _WEEK_DAYS:
                    if peut_prendre_role(p, role):
                        Y[p, v_idx, r_idx, j] = model.NewBoolVar(
                            f"Y_p{p.pompier_id}_v{v_idx}_r{r_idx}_j{j}"
                        )
                    else:
                        Y[p, v_idx, r_idx, j] = model.NewConstant(0)
    return Y


# =====================================================
# CONTRAINTES HARD
# =====================================================

def add_contrainte_max_jours(model, X, pompiers):
    """Maximum 5 jours de travail par semaine"""
    for p in pompiers:
        model.Add(sum(X[p, j] for j in _WEEK_DAYS) <= _MAX_WORKING_DAYS_PER_WEEK)


def add_contrainte_consecutifs(model, X, pompiers):
    """Maximum 3 jours consécutifs de travail"""
    for p in pompiers:
        # Fenêtres de 4 jours pour vraiment limiter à 3 jours consécutifs
        for j in range(4):
            model.Add(
                X[p, j] + X[p, j + 1] + X[p, j + 2] + X[p, j + 3] <= 3
            )


def add_contrainte_presence_journaliere(model, X, pompiers):
    """Minimum 10 pompiers par jour"""
    for j in _WEEK_DAYS:
        model.Add(sum(X[p, j] for p in pompiers) >= _MIN_FIREFIGHTERS_PER_DAY)


def add_contrainte_un_role_par_jour(model, Y, pompiers, vehicules):
    """Un pompier ne peut avoir qu'un seul rôle par jour"""
    for p in pompiers:
        for j in _WEEK_DAYS:
            model.Add(
                sum(
                    Y[p, v_idx, r_idx, j]
                    for v_idx, v in enumerate(vehicules)
                    for r_idx in range(len(v.roles))
                ) <= 1
            )


def add_contrainte_presence_role(model, X, Y, pompiers, vehicules):
    """Si un pompier a un rôle, il doit être présent"""
    for p in pompiers:
        for v_idx, v in enumerate(vehicules):
            for r_idx in range(len(v.roles)):
                for j in _WEEK_DAYS:
                    model.Add(Y[p, v_idx, r_idx, j] <= X[p, j])


def add_contrainte_disponibilites(model, X, pompiers, availability_map):
    """
    Empêche les pompiers de travailler les jours où ils sont indisponibles.

    Args:
        availability_map: dict[pompier_id, List[AvailabilitySlotFF]]
    """
    # Mapping Weekday -> index jour (0-6)
    weekday_to_index = {
        Weekday.MONDAY: 0,
        Weekday.TUESDAY: 1,
        Weekday.WEDNESDAY: 2,
        Weekday.THURSDAY: 3,
        Weekday.FRIDAY: 4,
        Weekday.SATURDAY: 5,
        Weekday.SUNDAY: 6
    }

    for p in pompiers:
        # Récupérer les disponibilités de ce pompier
        slots = availability_map.get(p.pompier_id, [])

        for slot in slots:
            # Si le pompier n'est PAS disponible ce jour
            if not slot.isAvailable:
                jour_index = weekday_to_index[slot.weekday]
                # Forcer X[p, jour] = 0 (ne travaille pas)
                model.Add(X[p, jour_index] == 0)

def add_contrainte_roles_vehicules(model, Y, pompiers, vehicules):
    """Un véhicule est soit complètement armé, soit vide"""
    for v_idx, v in enumerate(vehicules):
        for j in _WEEK_DAYS:
            vehicule_actif = model.NewBoolVar(f"vehicule_{v_idx}_actif_j{j}")

            for r_idx in range(len(v.roles)):
                nb_pompiers = sum(Y[p, v_idx, r_idx, j] for p in pompiers)
                model.Add(nb_pompiers == 1).OnlyEnforceIf(vehicule_actif)
                model.Add(nb_pompiers == 0).OnlyEnforceIf(vehicule_actif.Not())


# =====================================================
# OBJECTIF
# =====================================================

def add_objectif_maximiser_vehicules(model, X, Y, pompiers, vehicules):
    """
    Objectif :
    1. Maximiser le nombre de véhicules opérationnels
    2. Équilibrer les véhicules entre les jours (SOFT)
    3. Équilibrer les jours de travail entre pompiers
    """

    # Compter les véhicules actifs par jour
    vehicules_par_jour = []

    for j in _WEEK_DAYS:
        vehicules_ce_jour = []

        for v_idx, v in enumerate(vehicules):
            tous_roles_ok = []

            for r_idx in range(len(v.roles)):
                nb_pompiers = sum(Y[p, v_idx, r_idx, j] for p in pompiers)
                role_ok = model.NewBoolVar(f"role_{v_idx}_{r_idx}_ok_j{j}")

                model.Add(nb_pompiers == 1).OnlyEnforceIf(role_ok)
                model.Add(nb_pompiers != 1).OnlyEnforceIf(role_ok.Not())
                tous_roles_ok.append(role_ok)

            vehicule_ok = model.NewBoolVar(f"vehicule_{v_idx}_ok_j{j}")
            model.AddBoolAnd(tous_roles_ok).OnlyEnforceIf(vehicule_ok)
            model.AddBoolOr([r.Not() for r in tous_roles_ok]).OnlyEnforceIf(vehicule_ok.Not())

            vehicules_ce_jour.append(vehicule_ok)

        # Variable pour le nombre de véhicules ce jour
        nb_vehicules_jour = model.NewIntVar(0, len(vehicules), f"nb_vehicules_j{j}")
        model.Add(nb_vehicules_jour == sum(vehicules_ce_jour))
        vehicules_par_jour.append(nb_vehicules_jour)

    # ============ ÉQUILIBRE ENTRE JOURS (VERSION SIMPLE) ============
    # Calculer les écarts entre jours consécutifs
    ecarts_jours = []
    for j in range(6):  # Jours 0-5 (comparer avec jour suivant)
        ecart = model.NewIntVar(0, len(vehicules), f"ecart_j{j}_j{j + 1}")
        # Écart absolu entre jour j et jour j+1
        model.Add(ecart >= vehicules_par_jour[j] - vehicules_par_jour[j + 1])
        model.Add(ecart >= vehicules_par_jour[j + 1] - vehicules_par_jour[j])
        ecarts_jours.append(ecart)

    total_vehicules = sum(vehicules_par_jour)
    # ============ FIN ÉQUILIBRE ============

    # Équité entre pompiers
    totaux = {p: model.NewIntVar(0, 7, f"total_p{p.pompier_id}") for p in pompiers}
    for p in pompiers:
        model.Add(totaux[p] == sum(X[p, j] for j in _WEEK_DAYS))

    ecarts_pompiers = []
    moyenne_pompiers = 5
    for p in pompiers:
        ecart = model.NewIntVar(0, 7, f"ecart_p{p.pompier_id}")
        model.Add(ecart >= totaux[p] - moyenne_pompiers)
        model.Add(ecart >= moyenne_pompiers - totaux[p])
        ecarts_pompiers.append(ecart)

    # Objectif combiné
    model.Maximize(
        1000 * total_vehicules -  # Priorité 1: total
        100 * sum(ecarts_jours) -  # Priorité 2: réduire écarts entre jours
        1 * sum(ecarts_pompiers)  # Priorité 3: équité pompiers
    )

# =====================================================
# DIAGNOSTIC (optionnel, peut être désactivé en production)
# =====================================================

def diagnostic_complet(model, X, Y, pompiers, vehicules):
    """Diagnostic des ressources et conflits potentiels"""
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLET")
    print("=" * 60)

    # Variables Y
    Y_vars = sum(1 for var in Y.values() if not isinstance(var, int))
    Y_constants = sum(1 for var in Y.values() if isinstance(var, int))
    print(f"\n1. VARIABLES Y")
    print(f"   Variables: {Y_vars}, Constantes: {Y_constants}")

    # Ressources critiques
    print(f"\n2. RESSOURCES CRITIQUES")
    qualifs_rares = {}
    for v in vehicules:
        for role in v.roles:
            qualifs = [p for p in pompiers if p.a_qualification(role)]
            if len(qualifs) <= 2:
                qualifs_rares[role.name] = len(qualifs)

    if qualifs_rares:
        print("   ⚠️  Qualifications rares:")
        for qual, nb in sorted(qualifs_rares.items(), key=lambda x: x[1]):
            print(f"      {qual}: {nb} pompiers")

    # Besoins vs disponibilité
    print(f"\n3. BESOINS PAR QUALIFICATION (par jour)")
    besoins = {}
    for v in vehicules:
        for role in v.roles:
            besoins[role.name] = besoins.get(role.name, 0) + 1

    for qual_name, besoin in sorted(besoins.items()):
        dispo = sum(1 for p in pompiers if p.a_qualification(Qualification[qual_name]))
        ratio = dispo / besoin if besoin > 0 else 0
        status = "✓" if ratio >= 1 else "⚠️"
        print(f"   {status} {qual_name}: besoin={besoin}, dispo={dispo} (ratio={ratio:.1f})")

    # Conflits
    print(f"\n4. CONFLITS POTENTIELS")
    for qual_name, besoin in besoins.items():
        dispo = sum(1 for p in pompiers if p.a_qualification(Qualification[qual_name]))
        if dispo < besoin:
            print(f"   ❌ {qual_name}: besoin de {besoin - dispo} pompiers supplémentaires")

    print("\n" + "=" * 60 + "\n")


# =====================================================
# RÉSOLUTION ET GÉNÉRATION DU PLANNING
# =====================================================
def run_solver(
        model, X, Y, pompiers, vehicules, output_file=None
) -> Tuple[List[ShiftAssignmentCreationDto], List[VehicleAvailabilities]]:

    # =====================================================
    # MÉTRIQUES MODÈLE (AVANT SOLVE)
    # =====================================================
    proto = model.Proto()

    nb_vars = len(proto.variables)
    nb_constraints = len(proto.constraints)

    nb_bool_vars = sum(
        1 for v in proto.variables if v.domain == [0, 1]
    )

    nb_linear_ct = sum(
        1 for c in proto.constraints if c.HasField("linear")
    )

    nb_bool_or = sum(
        1 for c in proto.constraints if c.HasField("bool_or")
    )

    nb_bool_and = sum(
        1 for c in proto.constraints if c.HasField("bool_and")
    )

    nb_enforced = sum(
        1 for c in proto.constraints if len(c.enforcement_literal) > 0
    )

    print("\n" + "=" * 60)
    print("MÉTRIQUES DU MODÈLE (AVANT RÉSOLUTION)")
    print("=" * 60)
    print(f"Variables totales          : {nb_vars}")
    print(f"  └─ Booléennes            : {nb_bool_vars}")
    print(f"Contraintes totales        : {nb_constraints}")
    print(f"  ├─ Linéaires             : {nb_linear_ct}")
    print(f"  ├─ BoolOr                : {nb_bool_or}")
    print(f"  ├─ BoolAnd               : {nb_bool_and}")
    print(f"  └─ Conditionnelles       : {nb_enforced}")

    # =====================================================
    # SOLVEUR
    # =====================================================
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    # =====================================================
    # MÉTRIQUES SOLVEUR (APRÈS RÉSOLUTION)
    # =====================================================
    print("\n" + "=" * 60)
    print("MÉTRIQUES DU SOLVEUR")
    print("=" * 60)
    print(f"Statut                     : {solver.StatusName(status)}")
    print(f"Temps mur                  : {solver.WallTime():.3f}s")
    print(f"Temps CPU                  : {solver.UserTime():.3f}s")
    print(f"Branches explorées          : {solver.NumBranches()}")
    print(f"Conflits                   : {solver.NumConflicts()}")
    print(f"Valeur objectif            : {solver.ObjectiveValue()}")
    print(f"Workers                    : {solver.parameters.num_search_workers}")
    print(f"Limite temps               : {solver.parameters.max_time_in_seconds}s")

    # =====================================================
    # SI PAS DE SOLUTION
    # =====================================================
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("❌ Aucune solution trouvée")
        return [], []

    # =====================================================
    # (LE RESTE DE LA FONCTION EST STRICTEMENT INCHANGÉ)
    # =====================================================
    jours_noms = [
        Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY,
        Weekday.THURSDAY, Weekday.FRIDAY, Weekday.SATURDAY, Weekday.SUNDAY
    ]

    shift_assignments = []
    planning_lignes = []

    for p in pompiers:
        ligne = f"{p.prenom} {p.nom:15} : "
        for j in range(7):
            travaille = solver.Value(X[p, j])
            ligne += "⬜ " if travaille else "🟥 "

            shift_assignments.append(ShiftAssignmentCreationDto(
                weekday=jours_noms[j],
                shiftType=ShiftType.ON_SHIFT if travaille else ShiftType.OFF_DUTY,
                firefighterId=p.pompier_id
            ))
        planning_lignes.append(ligne)

    vehicle_availabilities = []

    vehicles_by_base_id = {}
    for v in vehicules:
        base_id = v.vehicule_id.rsplit('_', 1)[0] if '_' in v.vehicule_id else v.vehicule_id
        vehicles_by_base_id.setdefault(base_id, []).append(v)

    for base_id, vehicle_instances in vehicles_by_base_id.items():
        for j in range(7):
            available_count = 0
            for v_idx, v in enumerate(vehicules):
                if v not in vehicle_instances:
                    continue
                if all(
                    sum(solver.Value(Y[p, v_idx, r_idx, j]) for p in pompiers) == 1
                    for r_idx in range(len(v.roles))
                ):
                    available_count += 1

            vehicle_availabilities.append(VehicleAvailabilities(
                vehicleId=base_id,
                availableCount=available_count,
                weekday=jours_noms[j]
            ))

    if output_file:
        _write_planning_file(output_file, planning_lignes, solver, Y, pompiers, vehicules, jours_noms)

    return shift_assignments, vehicle_availabilities


def _write_planning_file(output_file, planning_lignes, solver, Y, pompiers, vehicules, jours_noms):
    """Écrit le planning détaillé dans un fichier"""

    def determiner_composition_vehicules(jour):
        composition = []
        for v_idx, vehicule in enumerate(vehicules):
            equipage = []
            roles_assignes = set()

            for p in pompiers:
                for r_idx, role in enumerate(vehicule.roles):
                    if solver.Value(Y[p, v_idx, r_idx, jour]) == 1:
                        equipage.append((p, role))
                        roles_assignes.add(r_idx)

            manquants = {}
            for r_idx, role in enumerate(vehicule.roles):
                if r_idx not in roles_assignes:
                    manquants[role.name] = manquants.get(role.name, 0) + 1

            composition.append({
                "vehicule": type(vehicule).__name__,
                "complet": len(manquants) == 0,
                "equipage": equipage,
                "manquants": manquants,
                "roles_totaux": len(vehicule.roles),
                "roles_remplis": len(roles_assignes)
            })
        return composition

    with open(_OUTPUT_DIR / output_file, "w", encoding="utf-8") as f:
        f.write("PLANNING HEBDOMADAIRE\n")
        f.write("=" * 60 + "\n\n")

        f.write("RÉPARTITION DES POMPIERS\n")
        f.write("-" * 60 + "\n")
        for ligne in planning_lignes:
            f.write(ligne + "\n")

        f.write("\n" + "=" * 60 + "\n")

        for j in range(7):
            f.write(f"\n{jours_noms[j].name}\n")
            f.write("-" * 40 + "\n")

            compositions = determiner_composition_vehicules(j)

            for comp in compositions:
                statut = "✓ COMPLET" if comp["complet"] else "✗ INCOMPLET"
                f.write(f"\n{comp['vehicule']} ({statut}) - "
                        f"{comp['roles_remplis']}/{comp['roles_totaux']} rôles\n")

                if comp["equipage"]:
                    for p, role in comp["equipage"]:
                        f.write(f"  ✓ {p.prenom} {p.nom} [{role.name}]\n")
                else:
                    f.write("  (aucun pompier assigné)\n")

                if comp["manquants"]:
                    f.write("  Manquants: ")
                    f.write(", ".join(f"{n} {q}" for q, n in comp["manquants"].items()))
                    f.write("\n")

        # Statistiques
        f.write("\n" + "=" * 60 + "\n")
        f.write("STATISTIQUES\n")
        f.write("-" * 40 + "\n")

        total_roles = sum(len(v.roles) for v in vehicules) * 7
        roles_remplis = sum(
            1 for (p, v_idx, r_idx, j), var in Y.items()
            if solver.Value(var) == 1
        )

        f.write(f"Rôles assignés: {roles_remplis}/{total_roles} "
                f"({100 * roles_remplis / total_roles:.1f}%)\n")

        for j in range(7):
            compositions = determiner_composition_vehicules(j)
            complets = sum(1 for c in compositions if c["complet"])
            f.write(f"{jours_noms[j].name}: {complets}/{len(vehicules)} véhicules complets\n")


# =====================================================
# FONCTION PRINCIPALE
# =====================================================

@track_emissions()
async def solve(planning_id: str, output_file: Optional[str] = None) -> None:
    """Résout le planning et l'envoie à l'API"""

    # Récupération des données
    firefighters, vehicles, availability_map,week_number,year = await _get_data(planning_id)

    # Création du modèle
    model = cp_model.CpModel()
    X = _create_variables(model, firefighters)
    Y = create_role_assignments(model, firefighters, vehicles)

    # Diagnostic (peut être commenté en production)
    diagnostic_complet(model, X, Y, firefighters, vehicles)

    # Contraintes
    add_contrainte_max_jours(model, X, firefighters)
    add_contrainte_consecutifs(model, X, firefighters)
    add_contrainte_presence_journaliere(model, X, firefighters)
    add_contrainte_disponibilites(model, X, firefighters, availability_map)
    add_contrainte_un_role_par_jour(model, Y, firefighters, vehicles)
    add_contrainte_presence_role(model, X, Y, firefighters, vehicles)
    add_contrainte_roles_vehicules(model, Y, firefighters, vehicles)

    # Objectif
    add_objectif_maximiser_vehicules(model, X, Y, firefighters, vehicles)

    # Résolution
    shifts_assignment, vehicles_availabilities = run_solver(model, X, Y, firefighters, vehicles, output_file)

    # Envoi à l'API
    if shifts_assignment:
        await remote_client.finalize_planning(
            planning_id=planning_id,
            planning_finalization_dto=PlanningFinalizationDto(
                shiftAssignments=shifts_assignment,
                vehicleAvailabilities= vehicles_availabilities
            )
        )
        print("✓ Planning finalisé")
    else:
        print("❌ Pas de solution trouvée")


if __name__ == "__main__":
    if len(sys.argv) in [2, 3]:
        asyncio.run(solve(
            planning_id=sys.argv[1],
            output_file=sys.argv[2] if len(sys.argv) == 3 else None
        ))
    else:
        print("Usage: python -m src.solver <planning_id> [output_file]", file=sys.stderr)