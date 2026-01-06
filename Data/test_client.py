# test_fire_stations.py
import asyncio
import logging
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    from Data.config import settings
    from Data.Client import remote_client  # Adaptez l'import

    try:
        # Test 1: Récupérer toutes les fire stations
        logger.info("=== Test: Get all fire stations ===")
        all_stations = await remote_client.get_all_fire_stations()
        print(f"Nombre de fire stations: {len(all_stations)}")

        # Afficher les stations
        for i, station in enumerate(all_stations):
            print(f"\nStation {i + 1}:")
            print(f"  ID: {station.get('id')}")
            print(f"  Nom: {station.get('name')}")
            print(f"  Localisation: {station.get('location')}")
            print(f"  Véhicules: {station.get('vehicles', [])}")

        # Test 2: Récupérer une station spécifique (si des stations existent)
        if all_stations:
            first_station_id = all_stations[0].get('id')
            if first_station_id:
                logger.info(f"\n=== Test: Get fire station by ID ({first_station_id}) ===")
                station = await remote_client.get_fire_station_by_id(first_station_id)
                print(f"Détails de la station:")
                print(station)

    except Exception as e:
        logger.error(f"Erreur: {e}")
    finally:
        await remote_client.close()


if __name__ == "__main__":
    asyncio.run(main())