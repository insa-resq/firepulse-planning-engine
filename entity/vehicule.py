from typing import List, Optional
from enum import Enum
from dataclasses import dataclass
from .pompier import Pompier



class Vehicule:
    def __init__(self, vitesse: float):
        self.vitesse = vitesse
        self.taille_equipe = None# vitesse du véhicule
        self.conducteur: Optional[Pompier] = None
        self.chef: Optional[Pompier] = None
        self.equipe: List[Pompier] = []     # équipiers
        self.caserneid: Optional[int] = None
        self.vehicule_id: Optional[int] = None
        self.conditions: Optional[List[Qualification]] = None
    def set_conducteur(self, p: Pompier):
        self.conducteur = p

    def set_chef(self, p: Pompier):
        self.chef = p

    def get_conditions(self):
        return self.conditions

    def ajouter_equipier(self, p: Pompier):
        self.equipe.append(p)

    def __repr__(self):
        return (f"{self.__class__.__name__}(Chef={self.chef}, "
                f"Conducteur={self.conducteur}, "
                f"Équipe={[p.prenom for p in self.equipe]}, "
                f"Vitesse={self.vitesse})")


# =====================================================
# Sous-classes pour CHAQUE véhicule
# =====================================================

from entity.pompier import Qualification


class Ambulance(Vehicule):
    def __init__(self):
        super().__init__(vitesse=90)
        self.taille_equipe = 3
        self.conditions = {
            Qualification.CHEF_PE: 1,
            Qualification.COND_B: 1,
            Qualification.SUAP: 1
        }


class Canadair(Vehicule):
    def __init__(self):
        super().__init__(vitesse=250)
        self.taille_equipe = 2
        self.conditions = {
            Qualification.PERMIS_AVION: 1,
            Qualification.INC: 1
        }


class PetitCamion(Vehicule):
    def __init__(self):
        super().__init__(vitesse=70)
        self.taille_equipe = 4
        self.conditions = {
            Qualification.CHEF_PE: 1,
            Qualification.COND_B: 1,
            Qualification.INC: 2
        }


class MoyenCamion(Vehicule):
    def __init__(self):
        super().__init__(vitesse=65)
        self.taille_equipe = 5
        self.conditions = {
            Qualification.CHEF_ME: 1,
            Qualification.COND_C: 1,
            Qualification.INC: 3
        }


class GrandCamion(Vehicule):
    def __init__(self):
        super().__init__(vitesse=60)
        self.taille_equipe = 7
        self.conditions = {
            Qualification.CHEF_GE: 1,
            Qualification.COND_C: 1,
            Qualification.INC: 5
        }


class PetitBateau(Vehicule):
    def __init__(self):
        super().__init__(vitesse=40)
        self.taille_equipe = 4
        self.conditions = {
            Qualification.CHEF_PE: 1,
            Qualification.PERMIS_BATEAU: 1,  # Conducteur bateau
            Qualification.SAUVETEUR: 2       # 2 sauveteurs
        }


class GrandBateau(Vehicule):
    def __init__(self):
        super().__init__(vitesse=35)
        self.taille_equipe = 6
        self.conditions = {
            Qualification.CHEF_ME: 1,
            Qualification.PERMIS_BATEAU: 1,  # Conducteur bateau
            Qualification.SAUVETEUR: 4       # 4 sauveteurs
        }


class Helicoptere(Vehicule):
    def __init__(self):
        super().__init__(vitesse=200)
        self.taille_equipe = 3
        self.conditions = {
            Qualification.PERMIS_HELICOPTER: 1,  # Pilote
            Qualification.SAUVETEUR: 2           # 2 sauveteurs/équipiers
        }