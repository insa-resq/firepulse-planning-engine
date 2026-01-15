from typing import Optional, Dict
from src.entities.pompier import Qualification
from src.entities.vehicle import VehicleType


class Vehicule:
    def __init__(self, taille_equipe: int = 0, conditions: Optional[Dict[Qualification, int]] = None):
        self.taille_equipe: int = taille_equipe
        self.conditions = conditions
        self.caserne_id: Optional[str] = None
        self.vehicule_id: Optional[str] = None
        self.roles: list[Qualification] = []
        for qualif, nb in conditions.items():
            self.roles.extend([qualif] * nb)

    @staticmethod
    def from_vehicle_type(vehicle_type: VehicleType) -> 'Vehicule':
        mapping = {
            VehicleType.AMBULANCE: Ambulance,
            VehicleType.CANADAIR: Canadair,
            VehicleType.SMALL_TRUCK: PetitCamion,
            VehicleType.MEDIUM_TRUCK: MoyenCamion,
            VehicleType.LARGE_TRUCK: GrandCamion,
            VehicleType.SMALL_BOAT: PetitBateau,
            VehicleType.LARGE_BOAT: GrandBateau,
            VehicleType.HELICOPTER: Helicoptere,
        }
        return mapping[vehicle_type]()


# =====================================================
# Sous-classes pour CHAQUE véhicule
# =====================================================

class Ambulance(Vehicule):
    def __init__(self):
        super().__init__(
            taille_equipe=3,
            conditions={
                Qualification.CHEF_PE: 1,
                Qualification.COND_B: 1,
                Qualification.SUAP: 1
            }
        )

class Canadair(Vehicule):
    def __init__(self):
        super().__init__(
            taille_equipe=2,
            conditions={
                Qualification.PERMIS_AVION: 1,
                Qualification.INC: 1
            }
        )

class PetitCamion(Vehicule):
    def __init__(self):
        super().__init__(
            taille_equipe=4,
            conditions={
                Qualification.CHEF_PE: 1,
                Qualification.COND_B: 1,
                Qualification.INC: 2
            }
        )

class MoyenCamion(Vehicule):
    def __init__(self):
        super().__init__(
            taille_equipe=5,
            conditions={
                Qualification.CHEF_ME: 1,
                Qualification.COND_C: 1,
                Qualification.INC: 3
            }
        )

class GrandCamion(Vehicule):
    def __init__(self):
        super().__init__(
            taille_equipe=7,
            conditions={
                Qualification.CHEF_GE: 1,
                Qualification.COND_C: 1,
                Qualification.INC: 5
            }
        )

class PetitBateau(Vehicule):
    def __init__(self):
        super().__init__(
            taille_equipe=4,
            conditions={
                Qualification.CHEF_PE: 1,
                Qualification.COND_B: 1,  # Conducteur bateau
                Qualification.SUAP: 2  # 2 sauveteurs
            }
        )

class GrandBateau(Vehicule):
    def __init__(self):
        super().__init__(
            taille_equipe=6,
            conditions={
                Qualification.CHEF_ME: 1,
                Qualification.COND_C: 1,  # Conducteur bateau
                Qualification.SUAP: 4  # 4 sauveteurs
            }
        )

class Helicoptere(Vehicule):
    def __init__(self):
        super().__init__(
            taille_equipe=3,
            conditions={
                Qualification.PERMIS_AVION: 1,  # Pilote
                Qualification.SUAP: 2  # 2 sauveteurs/équipiers
            }
        )
