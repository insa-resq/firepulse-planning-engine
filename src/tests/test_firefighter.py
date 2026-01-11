import asyncio

from src.entities.firefighter import FirefighterFilters
from src.utils.remote_client import remote_client

async def main():
    try:
        # Récupérer une station
        first_station = (await remote_client.get_fire_stations())[0]
        station = await remote_client.get_fire_station(station_id=first_station.id)

        print(f"Station: {station.name} (ID: {station.id})")

        # Récupérer les pompiers sous forme d'objets Pompier
        pompiers = await remote_client.get_firefighters(
            filters=FirefighterFilters(stationId=station.id)
        )

        print(f"\n{len(pompiers)} pompier(s) trouvé(s):")
        print("=" * 60)

        for pompier in pompiers:
            print(f"\n{pompier.prenom} {pompier.nom}")
            print(f"  ID: {pompier.pompier_id}")
            print(f"  Grade: {pompier.grade.name if hasattr(pompier.grade, 'name') else pompier.grade}")
            print(f"  Qualifications: {pompier.qualifications}")

            # Compter les qualifications acquises
            nb_qualifs = sum(pompier.qualifications)
            print(f"  Nombre de qualifications: {nb_qualifs}/{len(pompier.qualifications)}")

    except Exception as e:
        print(f"Erreur: {e}")
    finally:
        await remote_client.close()


if __name__ == "__main__":
    asyncio.run(main())
