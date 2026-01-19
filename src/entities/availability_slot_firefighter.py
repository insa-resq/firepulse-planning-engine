from pydantic import BaseModel

from src.entities.availability_slot import Weekday


class AvailabilitySlotFF(BaseModel):
    weekday: Weekday
    isAvailable: bool
    firefighterId: str