from datetime import datetime

from pydantic import BaseModel

class FireStation(BaseModel):
    id: str
    createdAt: datetime
    updatedAt: datetime
    name: str
    latitude: float
    longitude: float
