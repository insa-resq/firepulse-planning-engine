from datetime import datetime
from enum import StrEnum
from typing import Optional, Dict

from pydantic import BaseModel

class Weekday(StrEnum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"

class AvailabilitySlot(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    year: int
    weekNumber: int
    weekday: Weekday
    isAvailable: bool
    firefighterId: str

class AvailabilitySlotFilters(BaseModel):
    year: Optional[int] = None
    weekNumber: Optional[int] = None
    weekday: Optional[Weekday] = None
    firefighterId: Optional[str] = None

    def as_dict(self) -> Dict[str, str]:
        return self.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )
