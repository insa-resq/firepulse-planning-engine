import asyncio
import logging
import time
from typing import Dict, Optional, List

import httpx

from src.entities.fire_station import FireStation
from src.entities.firefighter import FirefighterFilters, Firefighter
from src.entities.firefighter_training import FirefighterTrainingFilters, FirefighterTraining
from src.entities.vehicle import VehicleFilters, Vehicle
from src.entities.availability_slot import AvailabilitySlotFilters, AvailabilitySlot
from src.entities.planning import FinalizedPlanning, PlanningFinalizationDto, PlanningUpdateDto, Planning
from src.utils.config import settings

HttpHeaders = Dict[str, str]

_logger = logging.getLogger(__name__)

class _RemoteClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.REMOTE_API_BASE_URL)
        self._auth_token: Optional[str] = None
        self._last_auth_refresh_time: float = 0.0
        self._auth_refresh_lock = asyncio.Lock()

    async def close(self) -> None:
        """
        Closes the underlying HTTP client.
        """
        if not self._client.is_closed:
            await self._client.aclose()

    async def _get_headers(self, with_auth: bool = True) -> HttpHeaders:
        if not with_auth:
            return {
                "Content-Type": "application/json",
            }

        async with self._auth_refresh_lock:
            current_time = time.time()
            if (
                    (self._auth_token is None) or
                    (current_time - self._last_auth_refresh_time > settings.REMOTE_API_AUTH_TOKEN_REFRESH_INTERVAL_SECONDS)
            ):
                self._auth_token = await self.login()
                self._last_auth_refresh_time = current_time

            return {
                "Authorization": f"Bearer {self._auth_token}",
                "Content-Type": "application/json"
            }

    async def login(self) -> str:
        """
        Authenticates the client with the remote API.
        """
        _logger.info("Logging in to the remote API...")
        headers = await self._get_headers(with_auth=False)
        response = await self._client.post(
            url="accounts-service/auth/login",
            json={
                "email": settings.REMOTE_API_EMAIL,
                "password": settings.REMOTE_API_PASSWORD
            },
            headers=headers
        )
        response.raise_for_status()
        _logger.info("Logged in successfully!")
        token: Optional[str] = response.json().get("token")
        if token is None:
            raise ValueError("No token returned from the remote API.")
        return token

    async def get_fire_stations(self) -> List[FireStation]:
        """
        Retrieves all fire stations
        """
        _logger.info("Fetching all fire stations")
        headers = await self._get_headers()
        response = await self._client.get(
            url="registry-service/fire-stations",
            headers=headers
        )
        response.raise_for_status()
        return [FireStation.model_validate(item, extra="ignore") for item in response.json()]

    async def get_fire_station(self, station_id: str) -> FireStation:
        """
        Retrieves a fire station by its ID
        """
        _logger.info(f"Fetching fire station with ID: {station_id}")
        headers = await self._get_headers()
        response = await self._client.get(
            url=f"registry-service/fire-stations/{station_id}",
            headers=headers
        )
        response.raise_for_status()
        return FireStation.model_validate(response.json(), extra="ignore")

    async def get_firefighters(self, filters: Optional[FirefighterFilters] = None) -> List[Firefighter]:
        """
        Retrieves firefighters (either full list or based on the given filters).
        """
        _logger.info(f"Fetching firefighters with filters: {filters}")
        headers = await self._get_headers()
        response = await self._client.get(
            url="registry-service/firefighters",
            params=filters.as_dict() if filters is not None else None,
            headers=headers
        )
        response.raise_for_status()
        return [Firefighter.model_validate(item, extra="ignore") for item in response.json()]

    async def get_firefighter_trainings(self, filters: Optional[FirefighterTrainingFilters]) -> List[FirefighterTraining]:
        """
        Retrieves firefighter trainings (either full list or based on the given filters).
        """
        _logger.info(f"Fetching firefighter trainings with filters: {filters}")
        headers = await self._get_headers()
        response = await self._client.get(
            url="registry-service/firefighter-trainings",
            params=filters.as_dict() if filters is not None else None,
            headers=headers
        )
        response.raise_for_status()
        return [FirefighterTraining.model_validate(item, extra="ignore") for item in response.json()]

    async def get_vehicles(self, filters: Optional[VehicleFilters] = None) -> List[Vehicle]:
        """
        Retrieves vehicles (either full list or based on the given filters).
        """
        _logger.info(f"Fetching vehicles with filters: {filters}")
        headers = await self._get_headers()
        response = await self._client.get(
            url="registry-service/vehicles",
            params=filters.as_dict() if filters is not None else None,
            headers=headers
        )
        response.raise_for_status()
        return [Vehicle.model_validate(item, extra="ignore") for item in response.json()]

    async def get_availability_slots(self, filters: Optional[AvailabilitySlotFilters] = None) -> List[AvailabilitySlot]:
        """
        Retrieves availability slots (either full list or based on the given filters).
        """
        _logger.info(f"Fetching availability slots with filters: {filters}")
        headers = await self._get_headers()
        response = await self._client.get(
            url="registry-service/availability-slots",
            params=filters.as_dict() if filters is not None else None,
            headers=headers
        )
        response.raise_for_status()
        return [AvailabilitySlot.model_validate(item, extra="ignore") for item in response.json()]

    async def get_planning(self, planning_id: str) -> Planning:
        """
        Retrieves a planning by its ID
        """
        _logger.info(f"Fetching planning with ID: {planning_id}")
        headers = await self._get_headers()
        response = await self._client.get(
            url=f"planning-service/plannings/{planning_id}",
            headers=headers
        )
        response.raise_for_status()
        return Planning.model_validate(response.json(), extra="ignore")

    async def update_planning(self, planning_id: str, planning_update_dto: PlanningUpdateDto) -> Planning:
        """
        Updates a planning by its ID
        """
        _logger.info(f"Updating planning with ID: {planning_id}")
        headers = await self._get_headers()
        response = await self._client.patch(
            url=f"planning-service/plannings/{planning_id}",
            json=planning_update_dto.as_dict(),
            headers=headers
        )
        response.raise_for_status()
        return Planning.model_validate(response.json(), extra="ignore")

    async def finalize_planning(self, planning_id: str, planning_finalization_dto: PlanningFinalizationDto) -> FinalizedPlanning:
        """
        Finalizes a planning by its ID
        """
        _logger.info(f"Finalizing planning with ID: {planning_id}")
        headers = await self._get_headers()
        response = await self._client.post(
            url=f"planning-service/plannings/{planning_id}/finalize",
            json=planning_finalization_dto.as_dict(),
            headers=headers
        )
        response.raise_for_status()
        return FinalizedPlanning.model_validate(response.json(), extra="ignore")

remote_client = _RemoteClient()
