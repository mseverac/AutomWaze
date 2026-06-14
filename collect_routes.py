import os
import json
import logging
from datetime import datetime
import requests
import folium

from WazeRouteCalculator.WazeRouteCalculator import *

logger = logging.getLogger('WazeRouteCalculator.WazeRouteCalculator')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
logger.addHandler(handler)

ADDRESS_A = '12 rue albert camus nozay 91620, France'
ADDRESS_B = "48.74138311701822, 2.0928744250745597"#'rue des jeunes bois chateaufort 78117, France'#'Rond point du bois des roches chateaufort 78117, France' 

REGION = 'EU'

NTFY_URL = "https://ntfy.sh/AutomWazeNozaySafran_notification"

# Définition des deux trajets : (nom, départ, arrivée)
TRIPS = [
    ("aller", ADDRESS_A, ADDRESS_B),
    ("retour", ADDRESS_B, ADDRESS_A),
]


def process_trip(trip_name, from_address, to_address, out_dir):
    """Calcule toutes les routes pour un trajet donné et sauvegarde les fichiers."""
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

        total_time_min = sum(seg.get("crossTime", 0) for seg in results) / 60.0
        total_distance_m = sum(seg.get("length", 0) for seg in results)
        total_distance_km = total_distance_m / 1000.0

        route_name = r.get("name", f"route_{i}")

        route_data = {
            "index": i,
            "name": route_name,
            "time_minutes": round(total_time_min, 2),
            "distance_km": round(total_distance_km, 2),
            "coords": coords,
        }
        routes_summary.append(route_data)

        # JSON brut de la route
        json_path = os.path.join(out_dir, f"{trip_name}_route_{i}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(route_data, f, ensure_ascii=False, indent=2)

        # Carte HTML
        if coords:
            m = folium.Map(location=coords[0], zoom_start=12)
            folium.PolyLine(coords, color="blue", weight=5).add_to(m)
            html_file = os.path.join(out_dir, f"{trip_name}_route_{i}.html")
            m.save(html_file)

    # Résumé pour ce trajet
    summary_path = os.path.join(out_dir, f"{trip_name}_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(routes_summary, f, ensure_ascii=False, indent=2)

    return routes_summary


def main():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = os.path.join("data", timestamp)
    os.makedirs(out_dir, exist_ok=True)

    best_per_trip = {}

    for trip_name, from_addr, to_addr in TRIPS:
        print(f"--- Calcul du trajet : {trip_name} ---")
        summary = process_trip(trip_name, from_addr, to_addr, out_dir)
        print(summary)

        if summary:
            best = min(summary, key=lambda x: x["time_minutes"])
            best_per_trip[trip_name] = best

    # Construction du message de notification
    message_lines = []
    for trip_name, best in best_per_trip.items():
        message_lines.append(
            f"{trip_name.capitalize()} : {best['time_minutes']} min, "
            f"{best['distance_km']} km "
            f"(data/{timestamp}/{trip_name}_route_{best['index']}.html)"
        )

    message = "\n".join(message_lines)

    if message:
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={"Title": f"Trajets Waze - {timestamp}"}
        )

    print(f"Données enregistrées dans {out_dir}")


if __name__ == "__main__":
    main()