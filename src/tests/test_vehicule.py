import asyncio

from src.entities.vehicle import VehicleFilters
from src.utils.remote_client import remote_client

async def main():
    try:
        # Récupérer une station
        first_station = (await remote_client.get_fire_stations())[0]
        station = await remote_client.get_fire_station(station_id=first_station.id)

        print(f"Station: {station.name} (ID: {station.id})")
        print("=" * 60)

        # Récupérer les véhicules
        vehicules = await remote_client.get_vehicles(
            filters=VehicleFilters(stationId=station.id)
        )

        print(f"\nLISTE COMPLÈTE DES VÉHICULES:")
        print(f"Total: {len(vehicules)} véhicule(s)")
        print("-" * 60)

        if not vehicules:
            print("Aucun véhicule dans cette station")
            return

        # Afficher chaque véhicule avec ses détails
        for i, v in enumerate(vehicules, 1):
            dispo = "✓ DISPONIBLE" if v.disponible else "✗ INDISPONIBLE"
            print(f"\n{i}. {v.__class__.__name__}")
            print(f"   Statut: {dispo}")
            print(f"   ID: {v.vehicule_id}")
            print(f"   Type: {v.type_name}")
            print(f"   Taille équipe: {v.taille_equipe} personnes")
            print(f"   Numéro d'instance: {v.instance_num}")

            # Afficher les conditions requises
            if v.conditions:
                print(f"   Conditions requises:")
                for qualif, nombre in v.conditions.items():
                    print(f"     - {qualif.name}: {nombre} personne(s)")

        print("\n" + "=" * 60)

        # Statistiques
        disponibles = sum(1 for v in vehicules if v.disponible)
        print(f"RÉSUMÉ:")
        print(f"  • Véhicules disponibles: {disponibles}/{len(vehicules)}")

        # Compter par type
        types_count = {}
        for v in vehicules:
            type_name = v.__class__.__name__
            types_count[type_name] = types_count.get(type_name, 0) + 1

        if types_count:
            print(f"  • Répartition par type:")
            for type_name, count in types_count.items():
                print(f"    - {type_name}: {count}")

    except Exception as e:
        print(f"Erreur: {e}")
    finally:
        await remote_client.close()


if __name__ == "__main__":
    asyncio.run(main())
