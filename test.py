from  WazeRouteCalculator.WazeRouteCalculator import *
import folium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time


import requests



logger = logging.getLogger('WazeRouteCalculator.WazeRouteCalculator')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
logger.addHandler(handler)

from_address = '12 rue albert camus nozay 91620, France'
to_address = "48.74138311701822, 2.0928744250745597"#'rue des jeunes bois chateaufort 78117, France'#'Rond point du bois des roches chateaufort 78117, France' 
region = 'EU'
route = WazeRouteCalculator(from_address, to_address, region)
route.calc_route_info()

print("get route keys",route.get_route(1,0).keys())
print("result",route.get_route(1,0)["results"])
print("route keys " ,route.__dict__.keys())

print(" ")

route.calc_all_routes_info()


rs = route.get_route(5,0)

for i,r in enumerate(rs):

    coords = [
        (seg["path"]["y"], seg["path"]["x"])
        for seg in r["results"]
    ]

    print("coords", coords)
    # Création de la carte
    m = folium.Map(location=coords[0], zoom_start=12)

    folium.PolyLine(
        coords,
        color="blue",
        weight=5
    ).add_to(m)

    html_file = f"route_{i}.html"
    m.save(html_file)

    # Capture d'écran
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1200,1200")

    driver = webdriver.Chrome(options=options)
    driver.get(f"file:///home/mathijs/AutomWaze/{html_file}")

    time.sleep(3)  # laisse le temps aux tuiles de charger

    driver.save_screenshot(f"route_{i}.png")
    driver.quit()

route.calc_all_routes_info()


"""requests.post(
    "https://ntfy.sh/AutomWazeNozaySafran_notification",
    data=route.calc_all_routes_info()
)

print("Notification envoyée")"""
