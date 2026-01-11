from datetime import datetime
from enum import StrEnum
from typing import List, Dict

from pydantic import BaseModel

from src.entities.shift_assignment import ShiftAssignment, ShiftAssignmentCreationDto

class PlanningStatus(StrEnum):
    GENERATING = "GENERATING"
    FINALIZED = "FINALIZED"

class Planning(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    year: int
    weekNumber: int
    status: PlanningStatus
    stationId: str

class PlanningUpdateDto(BaseModel):
    status: PlanningStatus

    def as_dict(self) -> Dict[str, str]:
        return self.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )

class PlanningFinalizationDto(BaseModel):
    shiftAssignments: List[ShiftAssignmentCreationDto]

    def as_dict(self) -> Dict[str, str]:
        return self.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )

class FinalizedPlanning(BaseModel):
    planning: Planning
    shiftAssignments: List[ShiftAssignment]
