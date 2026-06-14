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

ADDRESS_A = '12 rue albert camus nozay 91620, France'
ADDRESS_B = "48.74138311701822, 2.0928744250745597"
REGION = 'EU'
NTFY_URL = "https://ntfy.sh/AutomWazeNozaySafran_notification"
DICT_PATH = "analysis/route_dictionary.json"
HAUSDORFF_THRESHOLD = 0.002  # 50m

TRIPS = [
    ("aller",  ADDRESS_A, ADDRESS_B),
    ("retour", ADDRESS_B, ADDRESS_A),
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
        # Coords lues directement dans le dictionnaire — aucun fichier a ouvrir
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
        print(f"  [WARN] Format inattendu pour representative_id: '{rep_id}' → {parts}")
        return None
    run_folder, trip_name, route_part = parts
    route_idx = route_part.replace("route", "")

    # Si trip_name est vide, cherche tous les fichiers JSON correspondants
    if not trip_name:
        run_path = os.path.join("data", run_folder)
        if not os.path.isdir(run_path):
            return None
        for filename in os.listdir(run_path):
            if filename.endswith(f"_route_{route_idx}.json"):
                json_path = os.path.join(run_path, filename)
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"  [INFO] Trouvé via scan : {json_path}")
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

        json_path = os.path.join(out_dir, f"{trip_name}_route_{i}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(route_data, f, ensure_ascii=False, indent=2)

        if coords:
            m = folium.Map(location=coords[0], zoom_start=12)
            folium.PolyLine(coords, color="blue", weight=5).add_to(m)
            m.save(os.path.join(out_dir, f"{trip_name}_route_{i}.html"))

    summary_path = os.path.join(out_dir, f"{trip_name}_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(routes_summary, f, ensure_ascii=False, indent=2)

    return routes_summary


# ─────────────────────────────────────────────
# CARTE + CAPTURE PNG
# ─────────────────────────────────────────────

def make_map_and_capture(coords, png_path, html_path):
    lat_center = (coords[0][0] + coords[-1][0]) / 2
    lon_center = (coords[0][1] + coords[-1][1]) / 2

    #lats = [c[0] for c in coords]
    #lons = [c[1] for c in coords]
    #max_range = max(max(lats) - min(lats), max(lons) - min(lons))
    #zoom = 14 if max_range < 0.02 else 13 if max_range < 0.05 else \ 12 if max_range < 0.15 else 11 if max_range < 0.4 else 10
    

    zoom = 12

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


# ─────────────────────────────────────────────
# NOTIFICATION NTFY AVEC PNG
# ─────────────────────────────────────────────

def send_notification(title, message, png_path=None):
    # Supprime tout caractère non-ASCII pour les headers HTTP (latin-1)
    def ascii_safe(s):
        return s.encode("ascii", errors="replace").decode("ascii")

    safe_title   = ascii_safe(title)
    safe_message = ascii_safe(message)

    if png_path and os.path.exists(png_path):
        url = NTFY_URL + "?message=" + requests.utils.quote(safe_message)
        with open(png_path, "rb") as f:
            requests.post(url, data=f, headers={
                "Title":        safe_title,
                "Content-Type": "image/png",
                "Filename":     os.path.basename(png_path),
            })
    else:
        requests.post(NTFY_URL,
                      data=message.encode("utf-8"),
                      headers={"Title": safe_title})

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir   = os.path.join("data", timestamp)
    os.makedirs(out_dir, exist_ok=True)

    # Chargement du dictionnaire de classification
    if os.path.exists(DICT_PATH):
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            route_dictionary = json.load(f)
        print(f"Dictionnaire chargé : {len(route_dictionary['routes'])} groupes.")
    else:
        route_dictionary = None
        print("Aucun dictionnaire trouvé — classification désactivée.")

    for trip_name, from_addr, to_addr in TRIPS:
        print(f"\n--- Calcul du trajet : {trip_name} ---")
        summary = process_trip(trip_name, from_addr, to_addr, out_dir)

        if not summary:
            continue

        # Meilleure route = la plus rapide
        best = min(summary, key=lambda x: x["time_minutes"])
        coords = best["coords"]

        # Classification
        if route_dictionary:
            group_key, user_name = classify_route(coords, route_dictionary)
            route_label = user_name if user_name else "Attention itineraire inconnu"
        else:
            group_key  = None
            route_label = "Classification non disponible"

        # PNG de la meilleure route
        png_path  = os.path.join(out_dir, f"{trip_name}_best.png")
        html_path = os.path.join(out_dir, f"{trip_name}_best.html")
        if coords:
            make_map_and_capture(coords, png_path, html_path)

        # Notification
        title   = f"Waze {trip_name.capitalize()}  {timestamp}"
        message = (
            f"Itineraire : {route_label}\n"
            f"Temps      : {best['time_minutes']} min\n"
            f"Distance   : {best['distance_km']} km\n"
            #f"Carte      : data/{timestamp}/{trip_name}_best.html"
        )
        print(message)
        send_notification(title, message, png_path)

    print(f"\nDonnées enregistrées dans {out_dir}")


if __name__ == "__main__":
    main()