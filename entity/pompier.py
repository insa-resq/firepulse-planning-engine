from enum import Enum, auto


class Grade(Enum):
    SAPEUR = auto()
    CAPORAL = auto()
    SERGENT = auto()
    ADJUDANT = auto()
    LIEUTENANT = auto()
    CAPITAINE = auto()


class Qualification(Enum):
    COND_B = 0
    COND_C = 1
    SUAP = 2
    INC = 3
    PERMIS_AVION = 4
    CHEF_PE = 5   # Sergent+
    CHEF_ME = 6  # Adjudant+
    CHEF_GE = 7  # Lieutenant+


class Pompier:
    def __init__(self, nom: str, prenom: str, station_id: str, pompier_id: int,
                 grade: Grade, qualifications=None):

        self.nom = nom
        self.prenom = prenom
        self.station_id = station_id
        self.pompier_id = pompier_id
        self.grade = grade

        # Initialise un tableau de booléens à False si non fourni
        if qualifications is None:
            self.qualifications = [False] * len(Qualification)
        else:
            self.qualifications = qualifications

    def ajouter_qualification(self, qualif: Qualification):
        self.qualifications[qualif.value] = True

    def a_qualification(self, qualif: Qualification) -> bool:
        return self.qualifications[qualif.value]

    def __repr__(self):
        return (f"Pompier({self.prenom} {self.nom}, Grade={self.grade.name}, "
                f"Station={self.station_id}, ID={self.pompier_id})")
