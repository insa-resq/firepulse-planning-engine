# test_pompiers.py
import asyncio


async def main():
    from Data.Client import remote_client

    try:
        # Récupérer toutes les stations
        stations = await remote_client.get_all_fire_stations()
        if not stations:
            print("Pas de stations trouvées")
            return

        # Prendre la première station
        station_id = stations[1].get('id')
        station_name = stations[1].get('name')

        print(f"Station: {station_name} (ID: {station_id})")

        # Récupérer les pompiers sous forme d'objets Pompier
        pompiers = await remote_client.get_pompiers_by_station(station_id)

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