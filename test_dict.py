import json


DICT_PATH = "analysis/route_dictionary.json"

with open(DICT_PATH, "r", encoding="utf-8") as f:
    route_dictionary = json.load(f)

# Compare representative coordinates for "aller normal" and "aller detour" groups
aller_normal = route_dictionary.get("aller normal", {})
aller_detour = route_dictionary.get("aller detour", {})

normal_coord = aller_normal.get("representative_coord")
detour_coord = aller_detour.get("representative_coord")

print("Aller Normal - Representative Coordinate:")
print(normal_coord)
print("\nAller Detour - Representative Coordinate:")
print(detour_coord)
print("\nComparison:")
print(f"Same coordinates: {normal_coord == detour_coord}")
if normal_coord and detour_coord:
    print(f"Difference: {[detour_coord[i] - normal_coord[i] for i in range(len(normal_coord))]}")

    
