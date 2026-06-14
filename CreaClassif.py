import os
import json
import time
import numpy as np
import folium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from collections import defaultdict

DATA_DIR = "data"
OUTPUT_DIR = "analysis/route_groups"
DICT_PATH = "analysis/route_dictionary.json"

HAUSDORFF_THRESHOLD = 0.0005  # 50m


# ─────────────────────────────────────────────
# CHARGEMENT
# ─────────────────────────────────────────────

def load_all_routes(data_dir):
    flat = []
    run_folders = sorted([
        f for f in os.listdir(data_dir)
        if os.path.isdir(os.path.join(data_dir, f))
    ])
    for run_folder in run_folders:
        run_path = os.path.join(data_dir, run_folder)
        for filename in sorted(os.listdir(run_path)):
            if not filename.endswith("summary.json"):
                continue
            trip_name = filename.replace("summary.json", "").strip("_")
            filepath = os.path.join(run_path, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                routes = json.load(f)
            for r in routes:
                flat.append({
                    "id":           f"{run_folder}__{trip_name}__route{r['index']}",
                    "run":          run_folder,
                    "trip":         trip_name,
                    "index":        r["index"],
                    "name":         r.get("name", ""),
                    "time_minutes": r["time_minutes"],
                    "distance_km":  r["distance_km"],
                    "coords":       r["coords"],
                })
    return flat


# ─────────────────────────────────────────────
# HAUSDORFF
# ─────────────────────────────────────────────

def hausdorff_distance(coords_a, coords_b):
    a = np.array(coords_a, dtype=np.float64)
    b = np.array(coords_b, dtype=np.float64)
    diff  = a[:, None, :] - b[None, :, :]
    dists = np.sqrt((diff ** 2).sum(axis=2))
    return max(dists.min(axis=1).max(), dists.min(axis=0).max())


def compare_hausdorff(coords_a, coords_b):
    if not coords_a or not coords_b:
        return False
    return hausdorff_distance(coords_a, coords_b) < HAUSDORFF_THRESHOLD


# ─────────────────────────────────────────────
# UNION-FIND
# ─────────────────────────────────────────────

def find_groups(flat_routes):
    n      = len(flat_routes)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    total = n * (n - 1) // 2
    done  = 0
    for i in range(n):
        for j in range(i + 1, n):
            done += 1
            if done % 50 == 0:
                print(f"  Comparaison {done}/{total}...", end="\r")
            if compare_hausdorff(flat_routes[i]["coords"], flat_routes[j]["coords"]):
                union(i, j)

    groups_dict = defaultdict(list)
    for i in range(n):
        groups_dict[find(i)].append(i)

    return sorted(groups_dict.values(), key=len, reverse=True)


# ─────────────────────────────────────────────
# CARTE + CAPTURE PNG
# ─────────────────────────────────────────────

def make_map_and_capture(coords, group_idx, out_dir):
    if not coords:
        return None, None

    lat_center = (coords[0][0] + coords[-1][0]) / 2
    lon_center = (coords[0][1] + coords[-1][1]) / 2

    lats      = [c[0] for c in coords]
    lons      = [c[1] for c in coords]
    max_range = max(max(lats) - min(lats), max(lons) - min(lons))
    zoom      = (14 if max_range < 0.02 else 13 if max_range < 0.05 else
                 12 if max_range < 0.15 else 11 if max_range < 0.4 else 10) + 1

    m = folium.Map(location=[lat_center, lon_center], zoom_start=zoom)
    folium.PolyLine(coords, color="royalblue", weight=5, opacity=0.85).add_to(m)
    folium.Marker(
        location=coords[0], popup="Départ", tooltip="Départ",
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)
    folium.Marker(
        location=coords[-1], popup="Arrivée", tooltip="Arrivée",
        icon=folium.Icon(color="red", icon="flag", prefix="fa"),
    ).add_to(m)

    html_path = os.path.join(out_dir, f"group_{group_idx:02d}_preview.html")
    png_path  = os.path.join(out_dir, f"group_{group_idx:02d}_preview.png")
    m.save(html_path)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1200,900")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(f"file://{os.path.abspath(html_path)}")
        time.sleep(4)
        driver.save_screenshot(png_path)
    finally:
        driver.quit()

    return html_path, png_path


# ─────────────────────────────────────────────
# SAISIE INTERACTIVE
# ─────────────────────────────────────────────

def ask_user_for_name(group_idx, members, representative):
    print(f"\n{'═'*65}")
    print(f"  GROUPE {group_idx}  -  {len(members)} occurrence(s)")
    print(f"  Exemple : {representative['id']}")
    print(f"  Temps   : {representative['time_minutes']} min")
    print(f"  Distance: {representative['distance_km']} km")
    print(f"  Voir le PNG : group_{group_idx:02d}_preview.png")
    print()
    name      = input("  Nom de cette route : ").strip()
    direction = input("  Direction (aller / retour / autre) : ").strip().lower()
    notes     = input("  Notes libres (laisser vide si aucune) : ").strip()
    return name, direction, notes


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(DICT_PATH), exist_ok=True)

    if os.path.exists(DICT_PATH):
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            route_dictionary = json.load(f)
        print(f"Dictionnaire existant charge ({len(route_dictionary['routes'])} routes).")
    else:
        route_dictionary = {
            "metadata": {
                "hausdorff_threshold_deg": HAUSDORFF_THRESHOLD,
                "hausdorff_threshold_m":   round(HAUSDORFF_THRESHOLD * 111_000),
            },
            "routes": {}
        }

    print("Chargement des routes...")
    flat_routes = load_all_routes(DATA_DIR)
    print(f"{len(flat_routes)} routes chargees.\n")

    print("Calcul des groupes Hausdorff (seuil 50m)...")
    groups = find_groups(flat_routes)
    print(f"\n{len(groups)} groupe(s) trouve(s).\n")

    already_named = set(route_dictionary["routes"].keys())

    for g_idx, member_indices in enumerate(groups, start=1):
        members        = [flat_routes[i] for i in member_indices]
        representative = max(members, key=lambda r: len(r["coords"]))
        group_key      = f"group_{g_idx:02d}"

        print(f"Generation carte groupe {g_idx}/{len(groups)}...")
        # On passe directement les coords — plus besoin de chercher dans les fichiers
        html_path, png_path = make_map_and_capture(
            representative["coords"], g_idx, OUTPUT_DIR
        )

        times = [r["time_minutes"] for r in members]
        dists = [r["distance_km"]  for r in members]

        group_entry = {
            "group_key":        group_key,
            "user_name":        "",
            "direction":        "",
            "notes":            "",
            # ← COORDS DU REPRÉSENTANT STOCKÉES DIRECTEMENT ICI
            "representative_coords": representative["coords"],
            "representative_id":     representative["id"],
            "stats": {
                "occurrences":     len(members),
                "time_avg_min":    round(sum(times) / len(times), 2),
                "time_min_min":    min(times),
                "time_max_min":    max(times),
                "distance_avg_km": round(sum(dists) / len(dists), 2),
            },
            "preview_png":  png_path,
            "preview_html": html_path,
            "members": [
                {
                    "id":           r["id"],
                    "run":          r["run"],
                    "trip":         r["trip"],
                    "time_minutes": r["time_minutes"],
                    "distance_km":  r["distance_km"],
                }
                for r in members
            ],
        }

        if group_key in already_named:
            print(f"  Groupe {g_idx} deja nomme : '{route_dictionary['routes'][group_key]['user_name']}'.")
            # Met a jour stats, membres et coords sans ecraser le nom
            route_dictionary["routes"][group_key]["stats"]                = group_entry["stats"]
            route_dictionary["routes"][group_key]["members"]              = group_entry["members"]
            route_dictionary["routes"][group_key]["representative_coords"] = group_entry["representative_coords"]
        else:
            name, direction, notes = ask_user_for_name(g_idx, members, representative)
            group_entry["user_name"]  = name
            group_entry["direction"]  = direction
            group_entry["notes"]      = notes
            route_dictionary["routes"][group_key] = group_entry

        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(route_dictionary, f, ensure_ascii=False, indent=2)

    print(f"\n{'═'*65}")
    print("  DICTIONNAIRE FINAL")
    print(f"{'═'*65}")
    for key, entry in route_dictionary["routes"].items():
        print(f"\n  [{key}] '{entry['user_name']}' ({entry['direction']})")
        print(f"  {entry['stats']['occurrences']} occurrences - "
              f"moy {entry['stats']['time_avg_min']} min - "
              f"{entry['stats']['distance_avg_km']} km")
        if entry["notes"]:
            print(f"  Notes : {entry['notes']}")

    print(f"\nDictionnaire sauvegarde : {DICT_PATH}")
    print(f"Cartes et PNG dans      : {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()