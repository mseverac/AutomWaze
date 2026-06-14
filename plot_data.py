import os
import json
import time
import folium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

DATA_DIR = "data"
OUTPUT_DIR = "plots"

# Palette de couleurs cyclique pour les routes
COLORS = [
    "blue", "red", "green", "purple", "orange",
    "navy", "darkred", "darkgreen", "darkblue", "darkorange",
]


def load_all_summaries(run_path):
    """
    Charge tous les fichiers *summary.json d'un dossier de run.
    Retourne une liste de (trip_name, routes_summary).
    """
    trips = []
    for filename in sorted(os.listdir(run_path)):
        if filename.endswith("summary.json"):
            trip_name = filename.replace("summary.json", "")
            filepath = os.path.join(run_path, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                routes = json.load(f)
            if routes:
                trips.append((trip_name, routes))
    return trips


def capture_screenshot(html_abs_path, png_abs_path):
    """Lance un Chrome headless pour capturer la carte HTML en PNG."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1200,900")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(f"file://{html_abs_path}")
        time.sleep(4)  # laisse charger les tuiles folium
        driver.save_screenshot(png_abs_path)
    finally:
        driver.quit()


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    run_folders = sorted([
        f for f in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR, f))
    ])

    if not run_folders:
        print("Aucun dossier trouvé dans data/")
        return

    for run_folder in run_folders:
        run_path = os.path.join(DATA_DIR, run_folder)

        trips = load_all_summaries(run_path)
        if not trips:
            print(f"[{run_folder}] Aucun summary trouvé, ignoré.")
            continue

        # Carte combinée : toutes les routes de tous les trajets
        first_coords = trips[0][1][0]["coords"]
        m = folium.Map(location=first_coords[0], zoom_start=12)

        color_index = 0
        for trip_name, routes in trips:
            for r in routes:
                coords = r.get("coords", [])
                if not coords:
                    continue
                color = COLORS[color_index % len(COLORS)]
                tooltip = (
                    f"{trip_name} — route {r['index']} — "
                    f"{r.get('name', '')} — "
                    f"{r['time_minutes']} min — {r['distance_km']} km"
                )
                folium.PolyLine(
                    coords,
                    color=color,
                    weight=4,
                    tooltip=tooltip
                ).add_to(m)
                color_index += 1

        # Sauvegarde HTML
        html_filename = f"{run_folder}_all_routes.html"
        html_path = os.path.join(OUTPUT_DIR, html_filename)
        m.save(html_path)
        print(f"[{run_folder}] Carte HTML : {html_path}")

        # Capture PNG
        html_abs = os.path.abspath(html_path)
        png_path = os.path.join(OUTPUT_DIR, f"{run_folder}_all_routes.png")
        try:
            capture_screenshot(html_abs, png_path)
            print(f"[{run_folder}] Capture PNG : {png_path}")
        except Exception as e:
            print(f"[{run_folder}] Échec capture PNG : {e}")

    print("Terminé.")


if __name__ == "__main__":
    main()