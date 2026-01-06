import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Tuple

import httpx
from entity.pompier import Qualification
from entity.pompier import Grade
from entity.pompier import Pompier
from Data.config import settings


HttpHeaders = Dict[str, str]

logger = logging.getLogger(__name__)

class RemoteClient:
    _CACHE_TTL_SECONDS = 5 * 60 # 5 minutes
    _CACHE_MAX_SIZE = 5
    _AUTH_REFRESH_INTERVAL_SECONDS = 5 * 60 * 60 # 5 hours

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.REMOTE_API_BASE_URL)
        self._auth_token: Optional[str] = None
        self._last_auth_refresh_time: float = 0.0
        self._auth_refresh_lock = asyncio.Lock()
        #self._images_cache: Dict[str, Tuple[float, List[ImageDto]]] = {}
        self._images_cache_lock = asyncio.Lock()

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
            if (self._auth_token is None) or (current_time - self._last_auth_refresh_time > self._AUTH_REFRESH_INTERVAL_SECONDS):
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
        logger.info("Logging in to the remote API...")
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
        logger.info("Logged in successfully!")
        token: Optional[str] = response.json().get("token")
        if token is None:
            raise ValueError("No token returned from the remote API.")
        return token

    async def get_all_fire_stations(self) -> List[Dict]:
        """
        Récupère la liste de toutes les fire stations (admin seulement)
        GET /fire-stations
        """
        logger.info("Fetching all fire stations...")
        headers = await self._get_headers()

        try:
            response = await self._client.get(
                url="registry-service/fire-stations",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch fire stations: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching fire stations: {str(e)}")
            raise

    async def get_fire_station_by_id(self, station_id: str) -> Dict:
        """
        Récupère une fire station par son ID
        GET /fire-stations/{stationId}
        """
        logger.info(f"Fetching fire station with ID: {station_id}")
        headers = await self._get_headers()

        try:
            response = await self._client.get(
                url=f"registry-service/fire-stations/{station_id}",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Fire station {station_id} not found")
            else:
                logger.error(f"Failed to fetch fire station {station_id}: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching fire station {station_id}: {str(e)}")
            raise

    async def get_all_firefighters(self, station_id: Optional[str] = None) -> List[Dict]:
        """
        Récupère la liste de tous les firefighters
        GET /firefighters

        Si station_id est fourni, filtre par fire station
        """
        logger.info(f"Fetching firefighters for station_id: {station_id or 'all'}")
        headers = await self._get_headers()

        params = {}
        if station_id:
            params['stationId'] = station_id

        try:
            response = await self._client.get(
                url="registry-service/firefighters",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch firefighters: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching firefighters: {str(e)}")
            raise

    async def get_firefighter_trainings(self, firefighter_id: str) -> Optional[Dict]:
        """
        Récupère les trainings d'un firefighter
        GET /firefighter-trainings?firefighterId={id}
        """
        logger.info(f"Fetching trainings for firefighter ID: {firefighter_id}")
        headers = await self._get_headers()

        try:
            response = await self._client.get(
                url="registry-service/firefighter-trainings",
                params={"firefighterId": firefighter_id},
                headers=headers
            )
            response.raise_for_status()

            data = response.json()
            # Retourne le premier élément si c'est une liste, sinon retourne le dict directement
            if isinstance(data, list):
                return data[0] if data else None
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch trainings: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching trainings: {str(e)}")
            raise

    def _extract_qualifications_from_trainings(self, trainings_data: Optional[Dict]) -> List[bool]:
        """
        Extrait les qualifications booléennes depuis les données de training
        """
        # Initialiser toutes les qualifications à False
        qualifications = [False] * len(Qualification)

        if not trainings_data:
            return qualifications

        # Mapper les champs de l'API vers vos qualifications
        if trainings_data.get('permitB', False):
            qualifications[Qualification.COND_B.value] = True
        if trainings_data.get('permitC', False):
            qualifications[Qualification.COND_C.value] = True
        if trainings_data.get('suap', False):
            qualifications[Qualification.SUAP.value] = True
        if trainings_data.get('inc', False):
            qualifications[Qualification.INC.value] = True
        if trainings_data.get('permitAircraft', False):
            qualifications[Qualification.PERMIS_AVION.value] = True
        if trainings_data.get('smallTeamLeader', False):
            qualifications[Qualification.CHEF_PE.value] = True
        if trainings_data.get('mediumTeamLeader', False):
            qualifications[Qualification.CHEF_ME.value] = True
        if trainings_data.get('largeTeamLeader', False):
            qualifications[Qualification.CHEF_GE.value] = True
        # Note: permitBoat n'existe pas dans votre exemple, on garde False
        # Note: Les qualifications de chef sont basées sur le grade, pas sur le training

        return qualifications

    async def get_pompiers_by_station(self, station_id: str) -> List[Pompier]:
        """
        Récupère tous les pompiers d'une station et les convertit en objets Pompier
        """
        logger.info(f"Récupération des pompiers pour la station {station_id}")

        try:
            # 1. Récupérer les firefighters depuis l'API
            firefighters_data = await self.get_all_firefighters(station_id=station_id)

            pompiers = []

            for ff_data in firefighters_data:
                # 2. Récupérer les trainings pour ce firefighter
                trainings_data = await self.get_firefighter_trainings(ff_data.get('id'))

                # 3. Convertir les qualifications depuis les trainings
                qualifications = self._extract_qualifications_from_trainings(trainings_data)

                # 4. Convertir le grade depuis l'API vers l'énumération Grade
                grade = self._convert_grade(ff_data.get('rank', ''))

                # 5. Créer l'objet Pompier
                pompier = Pompier(
                    nom=ff_data.get('lastName', ''),
                    prenom=ff_data.get('firstName', ''),
                    station_id=station_id,
                    pompier_id=ff_data.get('id'),
                    grade=grade,
                    qualifications=qualifications
                )

                pompiers.append(pompier)

            return pompiers

        except Exception as e:
            logger.error(f"Erreur lors de la récupération des pompiers: {e}")
            raise

    def _convert_grade(self, api_grade: str) -> Grade:
        """
        Convertit le grade de l'API vers l'énumération Grade
        """
        grade_mapping = {
            'LIEUTENANT': Grade.LIEUTENANT,
            'CAPTAIN': Grade.CAPITAINE,
            'CHIEF': Grade.CAPITAINE,  # À adapter selon votre hiérarchie
            'FIREFIGHTER': Grade.SAPEUR,
            'TRAINEE': Grade.SAPEUR,
            'SERGEANT': Grade.SERGENT,
            'ADJUDANT': Grade.ADJUDANT,
            'CORPORAL': Grade.CAPORAL,
        }

        api_grade_upper = api_grade.upper() if api_grade else ''
        return grade_mapping.get(api_grade_upper, Grade.SAPEUR)
remote_client = RemoteClient()