import os
import json
import logging
import time
from datetime import datetime
import requests
import folium
import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from WazeRouteCalculator.WazeRouteCalculator import *

logger = logging.getLogger('WazeRouteCalculator.WazeRouteCalculator')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
logger.addHandler(handler)

ADDRESS_A  = '12 rue albert camus nozay 91620, France'
ADDRESS_B  = "48.74138311701822, 2.0928744250745597"       # Entree Est
ADDRESS_B2 = 'Rond point du bois des roches chateaufort 78117, France'  # Entree Sud

REGION           = 'EU'
DICT_PATH        = "analysis/route_dictionary.json"
HAUSDORFF_THRESHOLD = 0.002

TRIPS = [
    ("aller_Est",  ADDRESS_A,  ADDRESS_B),
    ("aller_Sud",  ADDRESS_A,  ADDRESS_B2),
    ("retour_Est", ADDRESS_B,  ADDRESS_A),
    ("retour_Sud", ADDRESS_B2, ADDRESS_A),
]


# ─────────────────────────────────────────────
# HAUSDORFF
# ─────────────────────────────────────────────

def hausdorff_distance(coords_a, coords_b):
    a = np.array(coords_a, dtype=np.float64)
    b = np.array(coords_b, dtype=np.float64)
    diff = a[:, None, :] - b[None, :, :]
    dists = np.sqrt((diff ** 2).sum(axis=2))
    return max(dists.min(axis=1).max(), dists.min(axis=0).max())


def classify_route(coords, route_dictionary):
    best_key  = None
    best_name = None
    best_dist = float("inf")

    print(f"[DEBUG] Classification contre {len(route_dictionary['routes'])} groupes...")

    for group_key, entry in route_dictionary["routes"].items():
        rep_coords = entry.get("representative_coords")
        if not rep_coords:
            print(f"  [WARN] Pas de representative_coords pour {group_key}")
            continue

        d = hausdorff_distance(coords, rep_coords)
        print(f"  [DEBUG] {group_key} '{entry['user_name']}' -> Hausdorff = {d:.6f} (seuil {HAUSDORFF_THRESHOLD})")

        if d < best_dist:
            best_dist = d
            best_key  = group_key
            best_name = entry["user_name"]

    if best_dist < HAUSDORFF_THRESHOLD:
        print(f"  [OK] Classee dans '{best_name}' (distance {best_dist:.6f})")
        return best_key, best_name

    print(f"  [WARN] Aucun groupe proche (meilleure distance {best_dist:.6f} > {HAUSDORFF_THRESHOLD})")
    return None, None


def load_representative_coords(entry):
    rep_id = entry.get("representative_id", "")
    parts = rep_id.split("__")
    if len(parts) != 3:
        print(f"  [WARN] Format inattendu pour representative_id: '{rep_id}' -> {parts}")
        return None
    run_folder, trip_name, route_part = parts
    route_idx = route_part.replace("route", "")

    if not trip_name:
        run_path = os.path.join("data", run_folder)
        if not os.path.isdir(run_path):
            return None
        for filename in os.listdir(run_path):
            if filename.endswith(f"_route_{route_idx}.json"):
                json_path = os.path.join(run_path, filename)
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"  [INFO] Trouve via scan : {json_path}")
                return data.get("coords")
        print(f"  [WARN] Aucun fichier route_{route_idx}.json dans {run_path}")
        return None

    json_path = os.path.join("data", run_folder, f"{trip_name}_route_{route_idx}.json")
    if not os.path.exists(json_path):
        print(f"  [WARN] Fichier introuvable : {json_path}")
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("coords")


# ─────────────────────────────────────────────
# WAZE
# ─────────────────────────────────────────────

def process_trip(trip_name, from_address, to_address, out_dir):
    route = WazeRouteCalculator(from_address, to_address, REGION)
    route.calc_route_info()
    route.calc_all_routes_info()
    all_routes = route.get_route(5, 0)

    routes_summary = []
    for i, r in enumerate(all_routes):
        results = r.get("results", [])
        coords = [
            (seg["path"]["y"], seg["path"]["x"])
            for seg in results
        ]
        total_time_min   = sum(seg.get("crossTime", 0) for seg in results) / 60.0
        total_distance_m = sum(seg.get("length",    0) for seg in results)

        route_data = {
            "index":        i,
            "name":         r.get("name", f"route_{i}"),
            "time_minutes": round(total_time_min, 2),
            "distance_km":  round(total_distance_m / 1000.0, 2),
            "coords":       coords,
        }
        routes_summary.append(route_data)

        # Sauvegarde JSON de chaque route individuelle
        json_path = os.path.join(out_dir, f"{trip_name}_route_{i}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(route_data, f, ensure_ascii=False, indent=2)

        # Carte HTML de chaque route
        if coords:
            m = folium.Map(location=coords[0], zoom_start=12)
            folium.PolyLine(coords, color="blue", weight=5).add_to(m)
            m.save(os.path.join(out_dir, f"{trip_name}_route_{i}.html"))

    # Résumé du trajet : toutes les routes triées du plus rapide au plus lent
    routes_summary.sort(key=lambda x: x["time_minutes"])
    summary_path = os.path.join(out_dir, f"{trip_name}_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(routes_summary, f, ensure_ascii=False, indent=2)

    best  = routes_summary[0]
    worst = routes_summary[-1]
    print(f"  Meilleure : route_{best['index']}  {best['time_minutes']} min  {best['distance_km']} km")
    print(f"  Moins bonne: route_{worst['index']} {worst['time_minutes']} min  {worst['distance_km']} km")

    return routes_summary


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir   = os.path.join("data", timestamp)
    os.makedirs(out_dir, exist_ok=True)

    if os.path.exists(DICT_PATH):
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            route_dictionary = json.load(f)
        print(f"Dictionnaire charge : {len(route_dictionary['routes'])} groupes.")
    else:
        route_dictionary = None
        print("Aucun dictionnaire trouve — classification desactivee.")

    run_summary = {}

    for trip_name, from_addr, to_addr in TRIPS:
        print(f"\n--- Calcul du trajet : {trip_name} ---")
        summary = process_trip(trip_name, from_addr, to_addr, out_dir)

        if not summary:
            continue

        best  = summary[0]   # deja trie par time_minutes dans process_trip
        worst = summary[-1]

        # Classification de la meilleure et de la moins bonne route
        for label, route_data in [("best", best), ("worst", worst)]:
            coords = route_data["coords"]
            if route_dictionary and coords:
                group_key, user_name = classify_route(coords, route_dictionary)
                route_data["route_label"] = user_name if user_name else "Itineraire inconnu"
                route_data["route_group"] = group_key
            else:
                route_data["route_label"] = "Classification non disponible"
                route_data["route_group"] = None

        run_summary[trip_name] = {
            "best":  best,
            "worst": worst,
            "all_routes_count": len(summary),
        }

    # Sauvegarde du resume global du run
    global_summary_path = os.path.join(out_dir, "run_summary.json")
    with open(global_summary_path, "w", encoding="utf-8") as f:
        json.dump(run_summary, f, ensure_ascii=False, indent=2)

    print(f"\nDonnees enregistrees dans {out_dir}")
    print(f"Resume global : {global_summary_path}")


if __name__ == "__main__":
    main()