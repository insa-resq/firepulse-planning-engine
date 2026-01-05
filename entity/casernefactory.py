# entity/caserne_factory.py

import random
from typing import List
from .caserne import Caserne
from .pompier import Pompier, Grade, Qualification
from .vehicule import (
    Ambulance, PetitCamion, MoyenCamion, GrandCamion,
    Canadair, PetitBateau, GrandBateau, Helicoptere
)


class CaserneFactory:
    PRENOMS = [
        "Alex", "Marie", "Thomas", "Julie", "Lucas", "Emma", "Hugo", "Lea",
        "Nina", "Maxime", "Clara", "Antoine", "Sarah", "Paul", "Eva", "Louis",
        "Chloe", "Noah", "Manon", "Arthur", "Jade", "Romain", "Alice", "Yanis",
        "Laura", "Theo", "Camille", "Nathan", "Lena", "Quentin"
    ]

    NOMS = [
        "Martin", "Durand", "Bernard", "Thomas", "Petit", "Robert", "Richard",
        "Roux", "Moreau", "Simon", "Laurent", "Lefevre", "Girard", "Andre",
        "Gauthier", "Garcia", "Fournier", "Dupont", "Lambert", "Bonnet"
    ]

    TYPES_CASERNE = {
        "urbaine": {"ambulances": 2, "petits_camions": 2, "moyens_camions": 1, "grands_camions": 1,
                    "canadairs": 0, "petits_bateaux": 0, "grands_bateaux": 0, "helicopteres": 0, "probabilite": 0.4},
        "periurbaine": {"ambulances": 2, "petits_camions": 1, "moyens_camions": 2, "grands_camions": 1,
                        "canadairs": 0, "petits_bateaux": 0, "grands_bateaux": 0, "helicopteres": 0, "probabilite": 0.3},
        "rurale": {"ambulances": 1, "petits_camions": 0, "moyens_camions": 1, "grands_camions": 2,
                   "canadairs": 1, "petits_bateaux": 0, "grands_bateaux": 0, "helicopteres": 0, "probabilite": 0.2},
        "mixte": {"ambulances": 2, "petits_camions": 1, "moyens_camions": 1, "grands_camions": 1,
                  "canadairs": 0, "petits_bateaux": 1, "grands_bateaux": 0, "helicopteres": 0, "probabilite": 0.05},
        "specialisee": {"ambulances": 1, "petits_camions": 0, "moyens_camions": 0, "grands_camions": 0,
                        "canadairs": 1, "petits_bateaux": 1, "grands_bateaux": 1, "helicopteres": 1, "probabilite": 0.05}
    }

    # =====================================================
    # Création des pompiers
    # =====================================================

    @staticmethod
    def creer_pompiers(nb: int, station_id: int) -> List[Pompier]:
        pompiers = []

        repartition_grades = (
            [Grade.SAPEUR] * 22 +
            [Grade.CAPORAL] * 12 +
            [Grade.SERGENT] * 8 +
            [Grade.ADJUDANT] * 4 +
            [Grade.LIEUTENANT] * 3 +
            [Grade.CAPITAINE] * 1
        )
        random.shuffle(repartition_grades)

        for i in range(nb):
            p = Pompier(
                nom=random.choice(CaserneFactory.NOMS),
                prenom=random.choice(CaserneFactory.PRENOMS),
                station_id=station_id,
                pompier_id=i,
                grade=repartition_grades[i]
            )

            # Qualifications
            p.ajouter_qualification(Qualification.INC if random.random() < 0.75 else Qualification.SUAP)

            if random.random() < 0.6:
                p.ajouter_qualification(Qualification.COND_B)

            if p.grade.value >= Grade.CAPORAL.value and random.random() < 0.3:
                p.ajouter_qualification(Qualification.COND_C)

            if p.grade.value >= Grade.SERGENT.value:
                p.ajouter_qualification(Qualification.CHEF_PE)

            if p.grade.value >= Grade.ADJUDANT.value:
                p.ajouter_qualification(Qualification.CHEF_ME)

            if p.grade.value >= Grade.LIEUTENANT.value:
                p.ajouter_qualification(Qualification.CHEF_GE)

            if random.random() < 0.07:
                p.ajouter_qualification(Qualification.PERMIS_AVION)

            if random.random() < 0.20:
                p.ajouter_qualification(Qualification.SAUVETEUR)

            pompiers.append(p)

        return pompiers

    # =====================================================
    # Création des véhicules
    # =====================================================

    @staticmethod
    def creer_vehicules(caserne_id: int, type_caserne: str) -> List:
        vehicules = []
        distribution = CaserneFactory.TYPES_CASERNE[type_caserne]

        for _ in range(distribution["ambulances"]):
            vehicules.append(Ambulance())
        for _ in range(distribution["petits_camions"]):
            vehicules.append(PetitCamion())
        for _ in range(distribution["moyens_camions"]):
            vehicules.append(MoyenCamion())
        for _ in range(distribution["grands_camions"]):
            vehicules.append(GrandCamion())
        for _ in range(distribution["canadairs"]):
            vehicules.append(Canadair())
        for _ in range(distribution["petits_bateaux"]):
            vehicules.append(PetitBateau())
        for _ in range(distribution["grands_bateaux"]):
            vehicules.append(GrandBateau())
        for _ in range(distribution["helicopteres"]):
            vehicules.append(Helicoptere())

        for i, v in enumerate(vehicules):
            v.id_vehicule = i
            v.caserneid = caserne_id

        return vehicules

    # =====================================================
    # Création d'une caserne complète
    # =====================================================

    @staticmethod
    def creer_caserne(nb_pompiers=50, station_id=1, type_caserne=None) -> Caserne:
        if type_caserne is None:
            types = list(CaserneFactory.TYPES_CASERNE.keys())
            poids = [CaserneFactory.TYPES_CASERNE[t]["probabilite"] for t in types]
            type_caserne = random.choices(types, weights=poids, k=1)[0]

        pompiers = CaserneFactory.creer_pompiers(nb_pompiers, station_id)
        vehicules = CaserneFactory.creer_vehicules(station_id, type_caserne)

        return Caserne(
            caserne_id=station_id,
            type_caserne=type_caserne,
            pompiers=pompiers,
            vehicules=vehicules
        )
