from datetime import datetime
from typing import Optional, Dict

from pydantic import BaseModel

class FirefighterTraining(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    permitB: bool
    permitC: bool
    permitAircraft: bool
    suap: bool
    inc: bool
    smallTeamLeader: bool
    mediumTeamLeader: bool
    largeTeamLeader: bool
    firefighterId: str

class FirefighterTrainingFilters(BaseModel):
    firefighterId: Optional[str] = None

    def as_dict(self) -> Dict[str, str]:
        return self.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )
