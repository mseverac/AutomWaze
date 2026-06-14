import os
import json
import folium

DATA_DIR = "data"
OUTPUT_DIR = "plots"

TRIP_COLORS = {
    "aller": ["blue", "navy", "deepskyblue", "purple", "darkblue"],
    "retour": ["red", "darkred", "orange", "salmon", "maroon"],
}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for run_folder in sorted(os.listdir(DATA_DIR)):
        run_path = os.path.join(DATA_DIR, run_folder)
        if not os.path.isdir(run_path):
            continue

        m = None

        for trip_name, colors in TRIP_COLORS.items():
            summary_path = os.path.join(run_path, f"{trip_name}_summary.json")
            if not os.path.exists(summary_path):
                continue

            with open(summary_path, "r", encoding="utf-8") as f:
                routes = json.load(f)

            if not routes:
                continue

            if m is None:
                first_coords = routes[0]["coords"]
                m = folium.Map(location=first_coords[0], zoom_start=12)

            for r in routes:
                coords = r["coords"]
                if not coords:
                    continue
                color = colors[r["index"] % len(colors)]
                tooltip = (
                    f"{trip_name} - {r['name']} - "
                    f"{r['time_minutes']} min - {r['distance_km']} km"
                )
                folium.PolyLine(
                    coords,
                    color=color,
                    weight=4,
                    tooltip=tooltip
                ).add_to(m)

        if m is not None:
            out_file = os.path.join(OUTPUT_DIR, f"{run_folder}_all_routes.html")
            m.save(out_file)
            print(f"Carte générée : {out_file}")


if __name__ == "__main__":
    main()