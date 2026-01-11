from datetime import datetime
from enum import StrEnum
from typing import Dict

from pydantic import BaseModel

from src.entities.availability_slot import Weekday

class ShiftType(StrEnum):
    ON_SHIFT = "ON_SHIFT"
    OFF_DUTY = "OFF_DUTY"
    ON_CALL = "ON_CALL"

class ShiftAssignment(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    weekday: Weekday
    shiftType: ShiftType
    firefighterId: str
    planningId: str

class ShiftAssignmentCreationDto(BaseModel):
    weekday: Weekday
    shiftType: ShiftType
    firefighterId: str

    def as_dict(self) -> Dict[str, str]:
        return self.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )
