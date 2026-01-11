from datetime import datetime
from enum import StrEnum
from typing import Optional, Dict

from pydantic import BaseModel

class VehicleType(StrEnum):
    AMBULANCE = "AMBULANCE"
    CANADAIR = "CANADAIR"
    SMALL_TRUCK = "SMALL_TRUCK"
    MEDIUM_TRUCK = "MEDIUM_TRUCK"
    LARGE_TRUCK = "LARGE_TRUCK"
    SMALL_BOAT = "SMALL_BOAT"
    LARGE_BOAT = "LARGE_BOAT"
    HELICOPTER = "HELICOPTER"

class Vehicle(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    type: VehicleType
    totalCount: int
    availableCount: int
    stationId: str

class VehicleFilters(BaseModel):
    stationId: Optional[str] = None
    type: Optional[VehicleType] = None

    def as_dict(self) -> Dict[str, str]:
        return self.model_dump(
            exclude_unset=True,
            exclude_none=True,
        )
