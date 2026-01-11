from typing import List, Dict
from .pompier import Pompier, Qualification
from .vehicule import Vehicule


class Caserne:
    """
    Représente une caserne de pompiers réelle.
    Contient les pompiers et les véhicules associés.
    """

    def __init__(
        self,
        caserne_id: int,
        type_caserne: str,
        pompiers: List[Pompier],
        vehicules: List[Vehicule]
    ):
        self.caserne_id = caserne_id
        self.type_caserne = type_caserne
        self.pompiers = pompiers
        self.vehicules = vehicules

    # -------------------------
    # Méthodes utilitaires
    # -------------------------

    def nombre_pompiers(self) -> int:
        return len(self.pompiers)

    def nombre_vehicules(self) -> int:
        return len(self.vehicules)

    def compter_vehicules_par_type(self):
        compteur = {}
        for v in self.vehicules:
            nom = v.__class__.__name__
            compteur[nom] = compteur.get(nom, 0) + 1
        return compteur

    def resume(self):
        print(f"Caserne {self.caserne_id}")
        print(f"  Type : {self.type_caserne}")
        print(f"  Pompiers : {len(self.pompiers)}")
        print(f"  Véhicules : {len(self.vehicules)}")

        for nom, nb in self.compter_vehicules_par_type().items():
            print(f"    {nom}: {nb}")

    def get_conditions(self) -> Dict[Qualification, int]:
        """
        Retourne un dictionnaire avec les qualifications nécessaires
        et le nombre de personnes requises pour chaque qualification.
        """
        qualifications_dict = {
            Qualification.COND_B: 0,
            Qualification.COND_C: 0,
            Qualification.SUAP: 0,
            Qualification.INC: 0,
            Qualification.PERMIS_AVION: 0,
            Qualification.PERMIS_HELICOPTER: 0,
            Qualification.PERMIS_BATEAU: 0,
            Qualification.CHEF_PE: 0,
            Qualification.CHEF_ME: 0,
            Qualification.CHEF_GE: 0
        }

        for vehicule in self.vehicules:
            for cond in vehicule.conditions:
                qualifications_dict[cond] +=1

        return qualifications_dict