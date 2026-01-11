from datetime import datetime
from enum import StrEnum
from typing import Optional, Dict

from pydantic import BaseModel

class FirefighterRank(StrEnum):
    SAPPER = "SAPPER"
    CORPORAL = "CORPORAL"
    SERGEANT = "SERGEANT"
    ADJUTANT = "ADJUTANT"
    LIEUTENANT = "LIEUTENANT"
    CAPTAIN = "CAPTAIN"

class Firefighter(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    firstName: str
    lastName: str
    rank: FirefighterRank
    userId: str
    stationId: str

class FirefighterFilters(BaseModel):
    stationId: Optional[str] = None
    rank: Optional[FirefighterRank] = None

    def as_dict(self) -> Dict[str, str]:
        return self.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )
