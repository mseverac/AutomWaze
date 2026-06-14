import os
import json
from collections import defaultdict

DATA_DIR = "data"
OUTPUT_DIR = "analysis"

def load_all_routes(data_dir):
    """
    Parcourt tout le dossier data/ et charge toutes les routes de tous les runs.
    Retourne un dict structuré : {run_folder: {trip_name: [route, ...]}}
    """
    all_data = {}

    run_folders = sorted([
        f for f in os.listdir(data_dir)
        if os.path.isdir(os.path.join(data_dir, f))
    ])

    for run_folder in run_folders:
        run_path = os.path.join(data_dir, run_folder)
        all_data[run_folder] = {}

        for filename in sorted(os.listdir(run_path)):
            if not filename.endswith("summary.json"):
                continue

            trip_name = filename.replace("summary.json", "").strip("_")
            filepath = os.path.join(run_path, filename)

            with open(filepath, "r", encoding="utf-8") as f:
                routes = json.load(f)

            if routes:
                all_data[run_folder][trip_name] = routes

    return all_data


def route_signature(coords, precision=3):
    """
    Génère une signature hashable d'une route à partir de ses coords.
    On arrondit pour absorber les micro-variations GPS entre deux runs.
    Utilise uniquement le premier, le dernier et N points intermédiaires
    pour rester robuste même si Waze renvoie des segments légèrement différents.
    """
    if not coords:
        return None

    # Sous-échantillonnage : 10 points répartis sur la route
    step = max(1, len(coords) // 10)
    sampled = coords[::step] + [coords[-1]]

    return tuple(
        (round(lat, precision), round(lon, precision))
        for lat, lon in sampled
    )


def build_flat_route_list(all_data):
    """
    Aplatit le dict hiérarchique en une liste de routes avec métadonnées complètes.
    Chaque entrée = une route identifiable par (run, trip, index).
    """
    flat = []
    for run_folder, trips in all_data.items():
        for trip_name, routes in trips.items():
            for r in routes:
                flat.append({
                    "id": f"{run_folder}__{trip_name}__route{r['index']}",
                    "run": run_folder,
                    "trip": trip_name,
                    "index": r["index"],
                    "name": r.get("name", ""),
                    "time_minutes": r["time_minutes"],
                    "distance_km": r["distance_km"],
                    "coords": r["coords"],
                    "signature": route_signature(r["coords"]),
                })
    return flat


def build_similarity_matrix(flat_routes):
    """
    Construit une matrice de similarité entre toutes les routes.
    Deux routes sont considérées identiques si leur signature correspond.
    Retourne :
      - matrix : dict {id_A: {id_B: True/False}}
      - groups : liste de groupes de routes identiques
    """
    ids = [r["id"] for r in flat_routes]
    sigs = {r["id"]: r["signature"] for r in flat_routes}

    matrix = {id_a: {} for id_a in ids}
    for i, id_a in enumerate(ids):
        for id_b in ids:
            matrix[id_a][id_b] = (
                sigs[id_a] is not None
                and sigs[id_a] == sigs[id_b]
            )

    # Groupes de routes identiques (union-find simplifié)
    visited = set()
    groups = []
    for id_a in ids:
        if id_a in visited:
            continue
        group = [id_b for id_b in ids if matrix[id_a][id_b]]
        for member in group:
            visited.add(member)
        if len(group) > 1:
            groups.append(group)

    return matrix, groups


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Chargement des routes...")
    all_data = load_all_routes(DATA_DIR)

    # 1. Sauvegarde du dict complet
    all_routes_path = os.path.join(OUTPUT_DIR, "all_routes.json")
    with open(all_routes_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"Toutes les routes exportées : {all_routes_path}")

    # 2. Liste aplatie
    flat_routes = build_flat_route_list(all_data)

    flat_path = os.path.join(OUTPUT_DIR, "flat_routes.json")
    # On retire la signature (tuple non sérialisable) avant export
    flat_export = [{k: v for k, v in r.items() if k != "signature"} for r in flat_routes]
    with open(flat_path, "w", encoding="utf-8") as f:
        json.dump(flat_export, f, ensure_ascii=False, indent=2)
    print(f"Liste aplatie exportée : {flat_path}")

    # 3. Matrice de similarité
    print("Construction de la matrice de similarité...")
    matrix, groups = build_similarity_matrix(flat_routes)

    # Export matrice (format lisible : liste de {id_a, id_b, same_route})
    matrix_export = []
    ids = [r["id"] for r in flat_routes]
    for i, id_a in enumerate(ids):
        for id_b in ids[i+1:]:  # triangle supérieur uniquement, sans diagonale
            matrix_export.append({
                "route_a": id_a,
                "route_b": id_b,
                "same_route": matrix[id_a][id_b],
            })

    matrix_path = os.path.join(OUTPUT_DIR, "similarity_matrix.json")
    with open(matrix_path, "w", encoding="utf-8") as f:
        json.dump(matrix_export, f, ensure_ascii=False, indent=2)
    print(f"Matrice de similarité exportée : {matrix_path}")

    # 4. Groupes de routes identiques
    groups_path = os.path.join(OUTPUT_DIR, "route_groups.json")
    with open(groups_path, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    print(f"Groupes de routes identiques exportés : {groups_path}")

    # 5. Résumé console
    print(f"\n{'='*60}")
    print(f"Routes analysées : {len(flat_routes)}")
    print(f"Groupes de routes identiques trouvés : {len(groups)}")
    for i, group in enumerate(groups):
        print(f"\n  Groupe {i+1} ({len(group)} occurrences) :")
        for member in group:
            r = next(x for x in flat_routes if x["id"] == member)
            print(f"    - {member}  [{r['time_minutes']} min, {r['distance_km']} km]")

    # 6. Stats par route canonique
    print(f"\n{'='*60}")
    print("Stats temporelles par groupe de route identique :\n")
    for i, group in enumerate(groups):
        times = [
            next(x for x in flat_routes if x["id"] == m)["time_minutes"]
            for m in group
        ]
        avg = round(sum(times) / len(times), 2)
        mn = min(times)
        mx = max(times)
        print(f"  Groupe {i+1} : moy={avg} min  min={mn} min  max={mx} min")


if __name__ == "__main__":
    main()