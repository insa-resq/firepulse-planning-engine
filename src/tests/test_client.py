import asyncio

from src.utils.remote_client import remote_client

async def main():
    try:
        # Test 1: Récupérer toutes les fire stations
        print("=== Test: Get all fire stations ===")
        all_stations = await remote_client.get_fire_stations()
        print(f"Nombre de fire stations: {len(all_stations)}")

        # Afficher les stations
        for i, station in enumerate(all_stations):
            print(f"\nStation {i + 1}:")
            print(f"  ID: {station.id}")
            print(f"  Nom: {station.name}")
            print(f"  Localisation: {station.latitude}, {station.longitude}")

        # Test 2: Récupérer une station spécifique (si des stations existent)
        if all_stations:
            first_station_id = all_stations[0].id
            if first_station_id:
                print(f"\n=== Test: Get fire station by ID ({first_station_id}) ===")
                station = await remote_client.get_fire_station(station_id=first_station_id)
                print(f"Détails de la station:")
                print(f"  ID: {station.id}")
                print(f"  Nom: {station.name}")
                print(f"  Localisation: {station.latitude}, {station.longitude}")

    except Exception as e:
        print(f"Erreur: {e}")
    finally:
        await remote_client.close()


if __name__ == "__main__":
    asyncio.run(main())