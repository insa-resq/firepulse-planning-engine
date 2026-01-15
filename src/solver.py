import asyncio
import sys
from pathlib import Path
from typing import List, Tuple, Final, Optional

from ortools.sat.python import cp_model

from build.lib.entities.planning import PlanningFinalizationDto
from src.entities.firefighter import FirefighterFilters
from src.entities.firefighter_training import FirefighterTrainingFilters
from src.entities.planning import PlanningUpdateDto, PlanningStatus
from src.entities.pompier import Qualification, Pompier, Grade
from src.entities.shift_assignment import ShiftAssignmentCreationDto
from src.entities.shift_assignment import ShiftType
from src.entities.vehicle import VehicleFilters
from src.entities.vehicule import Vehicule
from src.utils.remote_client import remote_client
from src.entities.availability_slot import  Weekday

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
def create_role_assignments(model, pompiers, vehicules):
    """
    Y[p, v, r, j] = 1 si le pompier p
    est affecté au rôle r
    sur le véhicule v
    le jour j
    """
    Y = {}

    for p in pompiers:
        for v_idx, v in enumerate(vehicules):
            for r_idx, role in enumerate(v.roles):
                for j in _WEEK_DAYS:
                    if p.a_qualification(role):
                        Y[p, v_idx, r_idx, j] = model.NewBoolVar(
                            f"Y_p{p.pompier_id}_v{v_idx}_r{r_idx}_j{j}"
                        )
                        print("1")
                    else:
                        # impossible → forcé à 0
                        Y[p, v_idx, r_idx, j] = model.NewConstant(0)
                        print("0")

    return Y


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

def add_contrainte_un_role_par_jour(model, Y, pompiers, vehicules):
    for p in pompiers:
        for j in _WEEK_DAYS:
            model.Add(
                sum(
                    Y[p, v_idx, r_idx, j]
                    for v_idx, v in enumerate(vehicules)
                    for r_idx, _ in enumerate(v.roles)
                ) <= 1
            )
def add_contrainte_presence_role(model, X, Y, pompiers, vehicules):
    for p in pompiers:
        for v_idx, v in enumerate(vehicules):
            for r_idx, _ in enumerate(v.roles):
                for j in _WEEK_DAYS:
                    model.Add(Y[p, v_idx, r_idx, j] <= X[p,j])


def add_contrainte_roles_vehicules(model, Y, pompiers, vehicules):
    """
    Contrainte : Un véhicule est soit complètement armé, soit vide.
    Pas de véhicules partiellement armés.
    """
    for v_idx, v in enumerate(vehicules):
        for j in _WEEK_DAYS:
            # Variable : ce véhicule est-il opérationnel ce jour ?
            vehicule_actif = model.NewBoolVar(f"vehicule_{v_idx}_actif_j{j}")

            # Pour chaque rôle
            for r_idx, role in enumerate(v.roles):
                nb_pompiers = sum(Y[p, v_idx, r_idx, j] for p in pompiers)

                # Si véhicule actif : exactement 1 pompier par rôle
                # Si véhicule inactif : 0 pompier par rôle
                model.Add(nb_pompiers == 1).OnlyEnforceIf(vehicule_actif)
                model.Add(nb_pompiers == 0).OnlyEnforceIf(vehicule_actif.Not())



# =====================================================
# 4) Objectif (équilibrer les jours travaillés)
# =====================================================

def add_soft_contrainte_completion_vehicules(model, X, pompiers, vehicules):
    """
    Contrainte SOFT qui valorise la complétion de chaque véhicule.
    Pour chaque véhicule et chaque jour, on vérifie si on peut le compléter.
    """
    HIERARCHIE_CHEFS = {
        Qualification.CHEF_PE: [Qualification.CHEF_PE],
        Qualification.CHEF_ME: [Qualification.CHEF_PE, Qualification.CHEF_ME],
        Qualification.CHEF_GE: [Qualification.CHEF_PE, Qualification.CHEF_ME, Qualification.CHEF_GE]
    }

    # Variables pour le manque de chaque véhicule chaque jour
    manques_vehicules = []

    for v_idx, vehicule in enumerate(vehicules):
        vehicule_manques_jour = []

        for j in _WEEK_DAYS:
            # Variable booléenne : véhicule complet ce jour ?
            vehicule_complet = model.NewBoolVar(f"vehicule_{v_idx}_complet_j{j}")

            # Variables pour vérifier chaque condition de qualification
            conditions_remplies = []

            # Pour chaque qualification requise par le véhicule
            for qualif, nombre_requis in vehicule.conditions.items():
                # Déterminer les qualifications valides (avec hiérarchie pour les chefs)
                if qualif in HIERARCHIE_CHEFS:
                    qualifications_valides = HIERARCHIE_CHEFS[qualif]
                else:
                    qualifications_valides = [qualif]

                # Compter les pompiers disponibles avec qualification valide
                disponibles_expr = []
                for p in pompiers:
                    for q_valide in qualifications_valides:
                        if p.a_qualification(q_valide):
                            disponibles_expr.append(X[p, j])
                            break  # Un pompier ne compte qu'une fois

                # Variable pour vérifier si la condition est remplie
                condition_ok = model.NewBoolVar(f"vehicule_{v_idx}_cond_{qualif.name}_j{j}")

                if disponibles_expr:
                    # Créer une contrainte : condition_ok = 1 si sum(disponibles_expr) >= nombre_requis
                    model.Add(sum(disponibles_expr) >= nombre_requis).OnlyEnforceIf(condition_ok)
                    model.Add(sum(disponibles_expr) < nombre_requis).OnlyEnforceIf(condition_ok.Not())
                else:
                    model.Add(condition_ok == 0)

                conditions_remplies.append(condition_ok)

            # Le véhicule est complet si TOUTES ses conditions sont remplies
            if conditions_remplies:
                model.AddBoolAnd(conditions_remplies).OnlyEnforceIf(vehicule_complet)
                model.AddBoolOr([c.Not() for c in conditions_remplies]).OnlyEnforceIf(vehicule_complet.Not())
            else:
                model.Add(vehicule_complet == 1)  # Si pas de conditions, toujours complet

            # Variable de manque : 0 si complet, 1 si incomplet
            manque = model.NewBoolVar(f"vehicule_{v_idx}_manque_j{j}")
            model.Add(manque == 1 - vehicule_complet)

            vehicule_manques_jour.append(manque)

        manques_vehicules.extend(vehicule_manques_jour)

    return manques_vehicules

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

def add_contrainte_roles_vehicules_souple(model, Y, pompiers, vehicules):
    """
    VERSION SOUPLE : Chaque rôle peut avoir 0 OU 1 pompier
    (au lieu de forcer exactement 1)
    """
    for v_idx, v in enumerate(vehicules):
        for r_idx, _ in enumerate(v.roles):
            for j in _WEEK_DAYS:
                # Maximum 1 pompier par rôle (mais peut être 0)
                model.Add(
                    sum(Y[p, v_idx, r_idx, j] for p in pompiers) <= 1
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
def add_objectif_maximiser_vehicules(model, X, Y, pompiers, vehicules):
    """
    Objectif : maximiser le nombre de véhicules opérationnels
    """

    # 1. Compter les véhicules actifs
    vehicules_actifs = []

    for v_idx, v in enumerate(vehicules):
        for j in _WEEK_DAYS:
            # Un véhicule est actif si tous ses rôles sont remplis
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

            vehicules_actifs.append(vehicule_ok)

    # 2. Équité entre pompiers
    totaux = {p: model.NewIntVar(0, 7, f"total_p{p.pompier_id}") for p in pompiers}
    for p in pompiers:
        model.Add(totaux[p] == sum(X[p, j] for j in _WEEK_DAYS))

    ecarts = []
    moyenne = 5
    for p in pompiers:
        ecart = model.NewIntVar(0, 7, f"ecart_p{p.pompier_id}")
        model.Add(ecart >= totaux[p] - moyenne)
        model.Add(ecart >= moyenne - totaux[p])
        ecarts.append(ecart)

    # Objectif combiné
    model.Maximize(
        1000 * sum(vehicules_actifs) -  # Priorité : véhicules complets
        1 * sum(ecarts)  # Secondaire : équité
    )


# =====================================================
# CORRECTION COMPLÈTE DU RUN_SOLVER
# =====================================================

# =====================================================
# CORRECTION COMPLÈTE DU RUN_SOLVER
# =====================================================

def run_solver(
        model,
        X,
        Y,
        pompiers,
        vehicules,
        output_file=None
) -> List[ShiftAssignmentCreationDto]:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    print(f"\n=== STATUT DU SOLVEUR : {solver.StatusName(status)} ===")
    print(f"Temps de résolution: {solver.WallTime():.2f}s")

    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print("❌ AUCUNE SOLUTION TROUVÉE")
        print(f"   Raison possible: contraintes incompatibles")
        return []

    jours_noms = [
        Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY,
        Weekday.THURSDAY, Weekday.FRIDAY, Weekday.SATURDAY, Weekday.SUNDAY
    ]

    # ----------------------------
    # 1. VÉRIFIER LES VALEURS DE Y
    # ----------------------------
    print("\n=== VÉRIFICATION DES ASSIGNATIONS Y ===")
    total_Y_assignes = 0

    for (p, v_idx, r_idx, j), var in Y.items():
        val = solver.Value(var)
        if val == 1:
            total_Y_assignes += 1
            vehicule = vehicules[v_idx]
            role = vehicule.roles[r_idx]
            print(f"✓ Jour {jours_noms[j].name}: {p.prenom} {p.nom} → "
                  f"{type(vehicule).__name__} [rôle {role.name}]")

    print(f"\nTOTAL: {total_Y_assignes} assignations Y trouvées")

    if total_Y_assignes == 0:
        print("\n⚠️  PROBLÈME: Aucune assignation Y trouvée!")
        print("   Vérifiez les contraintes sur Y")

    # ----------------------------
    # 2. CRÉER LES SHIFT ASSIGNMENTS
    # ----------------------------
    shift_assignments: List[ShiftAssignmentCreationDto] = []
    planning_lignes = []

    for p in pompiers:
        ligne = f"{p.prenom} {p.nom:15} : "
        for j in range(7):
            travaille = solver.Value(X[p, j])

            if travaille:
                ligne += "⬜ "
                shift_type = ShiftType.ON_SHIFT
            else:
                ligne += "🟥 "
                shift_type = ShiftType.OFF_DUTY

            shift_assignments.append(
                ShiftAssignmentCreationDto(
                    weekday=jours_noms[j],
                    shiftType=shift_type,
                    firefighterId=p.pompier_id
                )
            )

        planning_lignes.append(ligne)

    # ----------------------------
    # 3. COMPOSITION RÉELLE DES VÉHICULES
    # ----------------------------
    def determiner_composition_vehicules(jour):
        composition = []

        for v_idx, vehicule in enumerate(vehicules):
            equipage = []
            roles_assignes = set()

            # Parcourir TOUTES les variables Y pour ce véhicule ce jour
            for p in pompiers:
                for r_idx, role in enumerate(vehicule.roles):
                    if solver.Value(Y[p, v_idx, r_idx, jour]) == 1:
                        equipage.append((p, role))
                        roles_assignes.add(r_idx)

            # Calculer les rôles manquants
            manquants = {}
            for r_idx, role in enumerate(vehicule.roles):
                if r_idx not in roles_assignes:
                    role_name = role.name
                    manquants[role_name] = manquants.get(role_name, 0) + 1

            composition.append({
                "vehicule": type(vehicule).__name__,
                "complet": len(manquants) == 0,
                "equipage": equipage,
                "manquants": manquants,
                "roles_totaux": len(vehicule.roles),
                "roles_remplis": len(roles_assignes)
            })

        return composition

    # ----------------------------
    # 4. ÉCRITURE DU FICHIER
    # ----------------------------
    if output_file:
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

            # ----------------------------
            # STATISTIQUES GLOBALES
            # ----------------------------
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

            # Véhicules complets par jour
            for j in range(7):
                compositions = determiner_composition_vehicules(j)
                complets = sum(1 for c in compositions if c["complet"])
                f.write(f"{jours_noms[j].name}: {complets}/{len(vehicules)} "
                        f"véhicules complets\n")

    return shift_assignments


# =====================================================
# DIAGNOSTIC AMÉLIORÉ
# =====================================================

def diagnostic_complet(model, X, Y, pompiers, vehicules):
    """
    Diagnostic approfondi du problème
    """
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLET")
    print("=" * 60)

    # 1. Variables Y
    Y_vars = sum(1 for var in Y.values() if not isinstance(var, int))
    Y_constants = sum(1 for var in Y.values() if isinstance(var, int))
    print(f"\n1. VARIABLES Y")
    print(f"   Variables (non-constantes): {Y_vars}")
    print(f"   Constantes (à 0): {Y_constants}")
    print(f"   Total: {len(Y)}")

    # 1b. Vérifier la structure de Y
    print(f"\n   Exemple de clés Y:")
    for i, (key, var) in enumerate(Y.items()):
        if i >= 3:
            break
        p, v_idx, r_idx, j = key
        var_type = "Variable" if not isinstance(var, int) else "Constante"
        print(f"   {var_type}: pompier={p.nom}, véhicule={v_idx}, rôle={r_idx}, jour={j}")

    # 2. Ressources critiques
    print(f"\n2. RESSOURCES CRITIQUES")
    qualifs_rares = {}
    for v in vehicules:
        for role in v.roles:
            qualifs = [p for p in pompiers if p.a_qualification(role)]
            if len(qualifs) <= 2:  # Ressource rare
                qualifs_rares[role.name] = len(qualifs)

    if qualifs_rares:
        print("   ⚠️  Qualifications rares:")
        for qual, nb in sorted(qualifs_rares.items(), key=lambda x: x[1]):
            print(f"      {qual}: {nb} pompiers")

    # 3. Besoins vs disponibilité
    print(f"\n3. BESOINS PAR QUALIFICATION (par jour)")
    besoins = {}
    for v in vehicules:
        for role in v.roles:
            besoins[role.name] = besoins.get(role.name, 0) + 1

    for qual_name, besoin in sorted(besoins.items()):
        dispo = sum(1 for p in pompiers if p.a_qualification(
            Qualification[qual_name]))
        ratio = dispo / besoin if besoin > 0 else 0
        status = "✓" if ratio >= 1 else "⚠️"
        print(f"   {status} {qual_name}: besoin={besoin}, dispo={dispo} "
              f"(ratio={ratio:.1f})")

    # 4. Conflits potentiels
    print(f"\n4. CONFLITS POTENTIELS")
    for qual_name, besoin in besoins.items():
        dispo = sum(1 for p in pompiers if p.a_qualification(
            Qualification[qual_name]))
        if dispo < besoin:
            print(f"   ❌ {qual_name}: IMPOSSIBLE d'armer tous les véhicules")
            print(f"      → besoin de {besoin - dispo} pompiers supplémentaires")

    print("\n" + "=" * 60 + "\n")


# =====================================================
# FONCTION DE TEST DE L'OBJECTIF
# =====================================================

def tester_objectif_Y(model, X, Y, pompiers, vehicules):
    """
    Test pour vérifier que l'objectif fonctionne
    """
    print("\n=== TEST DE L'OBJECTIF ===")

    # Compter les variables non-constantes
    Y_reelles = [var for var in Y.values() if not isinstance(var, int)]
    print(f"Variables Y non-constantes: {len(Y_reelles)}")

    if len(Y_reelles) == 0:
        print("❌ PROBLÈME: Aucune variable Y à maximiser!")
        print("   Toutes les variables Y sont des constantes à 0")
        return

    # Vérifier qu'on peut construire l'objectif
    try:
        objectif = sum(Y_reelles)
        print(f"✓ Objectif construit: sum de {len(Y_reelles)} variables")
    except Exception as e:
        print(f"❌ Erreur lors de la construction de l'objectif: {e}")
        return

    # Vérifier les contraintes qui pourraient bloquer Y
    print("\n=== VÉRIFICATION DES CONTRAINTES BLOQUANTES ===")

    # Test: Y peut-il être > 0 ?
    for j in [0]:  # Tester juste le premier jour
        print(f"\nJour {j}:")
        for v_idx, vehicule in enumerate(vehicules):
            print(f"  Véhicule {v_idx} ({type(vehicule).__name__}):")
            for r_idx, role in enumerate(vehicule.roles):
                # Chercher les pompiers qui peuvent prendre ce rôle
                candidats = []
                for p in pompiers:
                    key = (p, v_idx, r_idx, j)
                    if key in Y and not isinstance(Y[key], int):
                        candidats.append(p.nom)

                if candidats:
                    print(f"    Rôle {r_idx} ({role.name}): {len(candidats)} candidats possibles")
                else:
                    print(f"    Rôle {r_idx} ({role.name}): ❌ AUCUN candidat (variables constantes)")

    print("\n" + "=" * 60)

def run_solver_debug(model, X, Y, pompiers, vehicules, output_file=None):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)

    if status != cp_model.OPTIMAL and status != cp_model.FEASIBLE:
        print(f"Aucune solution réalisable trouvée ! Status={status}")

    jours_noms = [
        Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY,
        Weekday.THURSDAY, Weekday.FRIDAY, Weekday.SATURDAY, Weekday.SUNDAY
    ]

    # 1. Vérifier X
    print("\n=== Debug : Shifts X ===")
    for p in pompiers:
        ligne = f"{p.prenom} {p.nom:15}: "
        for j in _WEEK_DAYS:
            val = solver.Value(X[p, j])
            ligne += f"{val} "
        print(ligne)

    # 2. Vérifier Y : candidats possibles pour chaque rôle
    print("\n=== Debug : Rôles Y ===")
    for j in _WEEK_DAYS:
        print(f"\n--- Jour {jours_noms[j].name} ---")
        for v_idx, vehicule in enumerate(vehicules):
            print(f"Véhicule {v_idx} ({type(vehicule).__name__})")
            for r_idx, role in enumerate(vehicule.roles):
                candidats = [p for p in pompiers if p.a_qualification(role)]
                val_assigned = [p for p in pompiers if solver.Value(Y[p, v_idx, r_idx, j])]
                print(f"  Rôle {r_idx} ({role.name}): candidats={len(candidats)}, assigné={len(val_assigned)}")
                if len(val_assigned) == 0:
                    print(f"    => Aucun pompier assigné !")

    # 3. Composition des véhicules comme avant
    def determiner_composition_vehicules(jour):
        composition = []
        for v_idx, vehicule in enumerate(vehicules):
            equipage = []
            manquants = {}
            for r_idx, role in enumerate(vehicule.roles):
                assignes = [p for p in pompiers if solver.Value(Y[p, v_idx, r_idx, jour])]
                if assignes:
                    for p in assignes:
                        equipage.append((p, role))
                else:
                    manquants[role.name] = 1
            composition.append({
                "vehicule": type(vehicule).__name__,
                "complet": len(manquants) == 0,
                "equipage": equipage,
                "manquants": manquants
            })
        return composition

    # 4. Affichage composition véhicules
    for j in _WEEK_DAYS:
        print(f"\n=== Composition véhicules jour {jours_noms[j].name} ===")
        compositions = determiner_composition_vehicules(j)
        for comp in compositions:
            print(f"{comp['vehicule']} : complet={comp['complet']}, manquants={comp['manquants']}")

    return None



@track_emissions()
async def solve(planning_id: str, output_file: Optional[str] = None) -> None:
    firefighters, vehicles = await _get_data(planning_id)

    model = cp_model.CpModel()
    X = _create_variables(model, firefighters)
    Y = create_role_assignments(model, firefighters, vehicles)

    # Diagnostic
    diagnostic_complet(model, X, Y, firefighters, vehicles)

    # Contraintes HARD
    add_contrainte_max_jours(model, X, firefighters)
    add_contrainte_consecutifs(model, X, firefighters)
    add_contrainte_presence_journaliere(model, X, firefighters)
    add_contrainte_un_role_par_jour(model, Y, firefighters, vehicles)
    add_contrainte_presence_role(model, X, Y, firefighters, vehicles)

    # ✓ Nouvelle contrainte : véhicules complets ou vides
    add_contrainte_roles_vehicules(model, Y, firefighters, vehicles)

    # ✓ Nouvel objectif : maximiser véhicules opérationnels
    add_objectif_maximiser_vehicules(model, X, Y, firefighters, vehicles)

    # Résolution
    shifts_assignment = run_solver(model, X, Y, firefighters, vehicles, output_file)

    if shifts_assignment:
        await remote_client.finalize_planning(planning_id=planning_id,
                                              planning_finalization_dto=PlanningFinalizationDto(
                                                  shiftAssignments=shifts_assignment))
        await remote_client.update_planning(planning_id=planning_id,
                                            planning_update_dto=PlanningUpdateDto(status=PlanningStatus.FINALIZED))
        print("✓ Planning finalisé")
    else:
        print("❌ Pas de solution trouvée")

# =====================================================
# DIAGNOSTIC SUPPLÉMENTAIRE
# =====================================================

def diagnostic_Y(model, X, Y, pompiers, vehicules):
    """
    Fonction pour diagnostiquer pourquoi Y reste à 0
    """
    print("\n=== DIAGNOSTIC Y ===")

    # Vérifier si des variables Y existent
    total_Y = sum(1 for var in Y.values() if not isinstance(var, int))
    print(f"Variables Y créées (non-constantes): {total_Y}")

    # Vérifier les qualifications
    for v_idx, v in enumerate(vehicules):
        print(f"\nVéhicule {v_idx} ({type(v).__name__}):")
        for r_idx, role in enumerate(v.roles):
            candidats = [p for p in pompiers if p.a_qualification(role)]
            print(f"  Rôle {role.name}: {len(candidats)} pompiers qualifiés")
            if len(candidats) == 0:
                print(f"    ⚠️  AUCUN POMPIER QUALIFIÉ POUR CE RÔLE!")


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
