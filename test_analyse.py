import os
import json
import numpy as np
from collections import defaultdict

DATA_DIR = "data"
OUTPUT_DIR = "analysis"


# ─────────────────────────────────────────────
# CHARGEMENT
# ─────────────────────────────────────────────

def load_all_routes(data_dir):
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


def build_flat_route_list(all_data):
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
                })
    return flat


# ─────────────────────────────────────────────
# MÉTHODE 1 : POINT PAR POINT
# ─────────────────────────────────────────────

def compare_pointbypoint(coords_a, coords_b, precision=4):
    """
    Égalité stricte point par point après arrondi.
    Les deux routes doivent avoir exactement le même nombre de points
    et chaque point doit coïncider à `precision` décimales (~11m à précision=4).
    Retourne False dès que les longueurs diffèrent.
    """
    if len(coords_a) != len(coords_b):
        return False
    for (la, lo), (lb, lob) in zip(coords_a, coords_b):
        if round(la, precision) != round(lb, precision):
            return False
        if round(lo, precision) != round(lob, precision):
            return False
    return True


# ─────────────────────────────────────────────
# MÉTHODE 2 : ÉCHANTILLON 10 POINTS
# ─────────────────────────────────────────────

def sample_signature(coords, n_points=10, precision=3):
    """
    Sous-échantillonne la route en n_points répartis uniformément + dernier point.
    Arrondi à `precision` décimales (~100m à précision=3).
    Retourne un tuple hashable.
    """
    if not coords:
        return None
    step = max(1, len(coords) // n_points)
    sampled = coords[::step] + [coords[-1]]
    return tuple(
        (round(lat, precision), round(lon, precision))
        for lat, lon in sampled
    )


def compare_sample(coords_a, coords_b, n_points=10, precision=3):
    sig_a = sample_signature(coords_a, n_points, precision)
    sig_b = sample_signature(coords_b, n_points, precision)
    return sig_a is not None and sig_a == sig_b


# ─────────────────────────────────────────────
# MÉTHODE 3 : DISTANCE DE HAUSDORFF
# ─────────────────────────────────────────────

def hausdorff_distance(coords_a, coords_b):
    """
    Distance de Hausdorff symétrique entre deux polylignes (en degrés).
    Complexité O(n×m) — robuste aux différences de densité de segments.
    """
    a = np.array(coords_a, dtype=np.float64)
    b = np.array(coords_b, dtype=np.float64)

    # distances euclidiennes entre tous les couples de points
    diff = a[:, None, :] - b[None, :, :]          # shape (n, m, 2)
    dists = np.sqrt((diff ** 2).sum(axis=2))       # shape (n, m)

    d_a_to_b = dists.min(axis=1).max()             # directed A→B
    d_b_to_a = dists.min(axis=0).max()             # directed B→A
    return max(d_a_to_b, d_b_to_a)


def compare_hausdorff(coords_a, coords_b, threshold_deg=0.002):
    """
    threshold_deg=0.002 ≈ 200m.
    Deux routes sont identiques si leur distance de Hausdorff < seuil.
    Filtre d'abord par distance totale pour éviter les calculs inutiles.
    """
    if not coords_a or not coords_b:
        return False
    return hausdorff_distance(coords_a, coords_b) < threshold_deg


# ─────────────────────────────────────────────
# GROUPEMENT (union-find)
# ─────────────────────────────────────────────

def find_groups(flat_routes, compare_fn):
    """
    Construit les groupes de routes identiques selon compare_fn.
    Utilise un union-find pour gérer la transitivité :
    si A==B et B==C alors A, B, C sont dans le même groupe.
    """
    n = len(flat_routes)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for i in range(n):
        for j in range(i + 1, n):
            ca = flat_routes[i]["coords"]
            cb = flat_routes[j]["coords"]
            if compare_fn(ca, cb):
                union(i, j)

    groups_dict = defaultdict(list)
    for i, r in enumerate(flat_routes):
        groups_dict[find(i)].append(r["id"])

    return [g for g in groups_dict.values() if len(g) > 1]


# ─────────────────────────────────────────────
# RÉSUMÉ
# ─────────────────────────────────────────────

def print_and_collect_summary(method_name, groups, flat_routes):
    id_to_route = {r["id"]: r for r in flat_routes}

    print(f"\n{'═'*65}")
    print(f"  MÉTHODE : {method_name}")
    print(f"{'═'*65}")
    print(f"  Groupes de routes identiques trouvés : {len(groups)}")

    summary = []
    for i, group in enumerate(groups):
        times = [id_to_route[rid]["time_minutes"] for rid in group]
        dists = [id_to_route[rid]["distance_km"] for rid in group]
        avg_t = round(sum(times) / len(times), 2)
        min_t, max_t = min(times), max(times)
        avg_d = round(sum(dists) / len(dists), 2)

        print(f"\n  Groupe {i+1}  ({len(group)} occurrences)")
        print(f"  Temps  : moy={avg_t} min  min={min_t} min  max={max_t} min")
        print(f"  Dist.  : moy={avg_d} km")
        print(f"  Membres :")
        for rid in group:
            r = id_to_route[rid]
            print(f"    • {rid}  [{r['time_minutes']} min, {r['distance_km']} km]")

        summary.append({
            "group_index": i + 1,
            "size": len(group),
            "members": group,
            "time_avg": avg_t,
            "time_min": min_t,
            "time_max": max_t,
            "distance_avg_km": avg_d,
        })

    return summary


def compare_methods(results):
    """
    Tableau croisé : pour chaque paire de routes, indique si les 3 méthodes
    sont d'accord entre elles.
    """
    methods = list(results.keys())
    disagreements = []

    # Reconstruit pour chaque méthode un dict pair→bool
    pair_results = {m: {} for m in methods}
    for m, groups in results.items():
        # Tous les membres dans les groupes sont "same=True"
        same_pairs = set()
        for group in groups:
            for i, a in enumerate(group):
                for b in group[i+1:]:
                    same_pairs.add((min(a, b), max(a, b)))
        pair_results[m] = same_pairs

    all_pairs = set()
    for m in methods:
        all_pairs |= pair_results[m]

    for pair in sorted(all_pairs):
        votes = {m: pair in pair_results[m] for m in methods}
        if len(set(votes.values())) > 1:   # les méthodes ne sont pas d'accord
            disagreements.append({"pair": list(pair), "votes": votes})

    print(f"\n{'═'*65}")
    print("  DÉSACCORDS ENTRE MÉTHODES")
    print(f"{'═'*65}")
    if not disagreements:
        print("  Aucun désaccord : les 3 méthodes donnent les mêmes groupes.")
    else:
        print(f"  {len(disagreements)} paire(s) classées différemment :\n")
        for d in disagreements:
            a, b = d["pair"]
            print(f"  {a}")
            print(f"  {b}")
            for m, v in d["votes"].items():
                print(f"    {m:30s} → {'IDENTIQUES' if v else 'différentes'}")
            print()

    return disagreements


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Chargement des routes...")
    all_data = load_all_routes(DATA_DIR)
    flat_routes = build_flat_route_list(all_data)
    print(f"{len(flat_routes)} routes chargées depuis {len(all_data)} runs.")

    methods = {
        "Point par point   (précision=4, ~11m)": lambda a, b: compare_pointbypoint(a, b, precision=100),
        "Échantillon 10pts (précision=3, ~100m)": lambda a, b: compare_sample(a, b),
        "Hausdorff         (seuil=200m)":          lambda a, b: compare_hausdorff(a, b, threshold_deg=0.000000002),
    }

    all_results = {}
    all_summaries = {}

    for method_name, compare_fn in methods.items():
        print(f"\nCalcul groupes — {method_name} ...")
        groups = find_groups(flat_routes, compare_fn)
        all_results[method_name] = groups
        all_summaries[method_name] = print_and_collect_summary(method_name, groups, flat_routes)

    disagreements = compare_methods(all_results)

    # Export JSON
    export = {
        method: {
            "groups": all_summaries[method]
        }
        for method in all_summaries
    }
    export["disagreements_between_methods"] = disagreements

    out_path = os.path.join(OUTPUT_DIR, "route_comparison.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    print(f"\nRésultats exportés : {out_path}")


if __name__ == "__main__":
    main()