# test_vehicules_final.py
import asyncio


async def main():
    from Data.Client import remote_client

    try:
        # Récupérer une station
        stations = await remote_client.get_all_fire_stations()
        if not stations:
            print("Pas de stations")
            return

        station_id = stations[0].get('id')
        station_name = stations[0].get('name')

        print(f"Station: {station_name} (ID: {station_id})")
        print("=" * 60)

        # Récupérer les véhicules
        vehicules = await remote_client.get_vehicules_by_station(station_id)

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
            print(f"   Vitesse: {v.vitesse} km/h")
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
        import traceback
        traceback.print_exc()
    finally:
        await remote_client.close()


if __name__ == "__main__":
    asyncio.run(main())