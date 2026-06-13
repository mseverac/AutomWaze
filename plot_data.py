import os
import json
import folium

DATA_DIR = "data"
OUTPUT_DIR = "plots"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for run_folder in sorted(os.listdir(DATA_DIR)):
        run_path = os.path.join(DATA_DIR, run_folder)
        if not os.path.isdir(run_path):
            continue

        summary_path = os.path.join(run_path, "summary.json")
        if not os.path.exists(summary_path):
            continue

        with open(summary_path, "r", encoding="utf-8") as f:
            routes = json.load(f)

        if not routes:
            continue

        # Carte combinée avec toutes les routes de ce run
        first_coords = routes[0]["coords"]
        m = folium.Map(location=first_coords[0], zoom_start=12)

        colors = ["blue", "red", "green", "purple", "orange"]

        for r in routes:
            coords = r["coords"]
            if not coords:
                continue
            color = colors[r["index"] % len(colors)]
            tooltip = f"{r['name']} - {r['time_minutes']} min - {r['distance_km']} km"
            folium.PolyLine(
                coords,
                color=color,
                weight=4,
                tooltip=tooltip
            ).add_to(m)

        out_file = os.path.join(OUTPUT_DIR, f"{run_folder}_all_routes.html")
        m.save(out_file)
        print(f"Carte générée : {out_file}")


if __name__ == "__main__":
    main()