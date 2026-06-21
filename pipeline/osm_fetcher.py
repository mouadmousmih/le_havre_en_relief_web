"""
Téléchargement des données OpenStreetMap via l'API Overpass.
Récupère routes, bâtiments (ways + relations avec cours intérieures) et espaces verts.
"""

import json
import time
import urllib.request
import urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


class OSMFetcher:

    def fetch(self, bbox: list, leisure_types: list = None) -> tuple:
        if leisure_types is None:
            leisure_types = ["park", "garden", "square"]

        lon_min, lat_min, lon_max, lat_max = bbox
        bb = f"{lat_min},{lon_min},{lat_max},{lon_max}"

        leisure_filter = "\n".join(
            f'  way["leisure"="{t}"];'
            for t in leisure_types
        )

        query = f"""
[out:json][timeout:60][bbox:{bb}];
(
  way["highway"];
  way["building"];
  relation["building"];
  {leisure_filter}
);
out geom;
"""
        print(f"[OSMFetcher] Téléchargement bbox {bb}...")

        url = OVERPASS_URL + "?data=" + urllib.parse.quote(query)

        for attempt in range(3):
            try:
                req  = urllib.request.Request(url, headers={"User-Agent": "tactile-map/1.0"})
                data = urllib.request.urlopen(req, timeout=90).read()
                break
            except Exception as e:
                print(f"  Tentative {attempt + 1}/3 échouée : {e}")
                if attempt < 2:
                    time.sleep(3)
                else:
                    raise

        elements = json.loads(data).get("elements", [])
        roads, buildings, green_areas = [], [], []

        for el in elements:
            el_type = el.get("type")
            tags    = el.get("tags", {})
            osm_id  = el.get("id", "")

            if el_type == "way":
                coords = [[n["lon"], n["lat"]] for n in el.get("geometry", [])]

                if "highway" in tags and len(coords) >= 2:
                    roads.append({
                        "id"          : osm_id,
                        "name"        : tags.get("name", ""),
                        "type"        : tags.get("highway", "unclassified"),
                        "junction"    : tags.get("junction", ""),
                        "coordinates" : coords,
                    })

                elif "building" in tags and len(coords) >= 3:
                    buildings.append({
                        "id"          : osm_id,
                        "name"        : tags.get("name", ""),
                        "type"        : tags.get("building", "yes"),
                        "coordinates" : [coords],
                        "inner_coords": [],
                        "height_m"    : self._get_height(tags),
                    })

                elif "leisure" in tags and tags["leisure"] in leisure_types and len(coords) >= 3:
                    green_areas.append({
                        "id"          : osm_id,
                        "name"        : tags.get("name", ""),
                        "leisure"     : tags.get("leisure", ""),
                        "coordinates" : coords,
                    })

            elif el_type == "relation" and "building" in tags:
                outer_rings, inner_rings = [], []

                for member in el.get("members", []):
                    if member.get("type") != "way":
                        continue
                    geom = member.get("geometry", [])
                    coords = [
                        [n["lon"], n["lat"]] for n in geom
                        if "lon" in n and "lat" in n
                    ]
                    if len(coords) < 3:
                        continue
                    role = member.get("role", "outer")
                    if role == "outer":
                        outer_rings.append(coords)
                    elif role == "inner":
                        inner_rings.append(coords)

                if not outer_rings:
                    continue

                outer = max(outer_rings, key=len)
                buildings.append({
                    "id"          : osm_id,
                    "name"        : tags.get("name", ""),
                    "type"        : tags.get("building", "yes"),
                    "coordinates" : [outer],
                    "inner_coords": inner_rings,
                    "height_m"    : self._get_height(tags),
                })

        print(f"[OSMFetcher] {len(roads)} routes  |  "
              f"{len(buildings)} bâtiments  |  "
              f"{len(green_areas)} espaces verts")
        return roads, buildings, green_areas


    def _get_height(self, tags: dict) -> float:
        if "height" in tags:
            try:
                return float(str(tags["height"]).replace("m", "").strip())
            except (ValueError, TypeError):
                pass
        if "building:levels" in tags:
            try:
                return float(tags["building:levels"]) * 3.0
            except (ValueError, TypeError):
                pass
        defaults = {
            "cathedral": 40.0, "church": 20.0, "mosque": 18.0,
            "tower": 30.0, "hospital": 18.0, "school": 9.0,
        }
        return defaults.get(tags.get("building", ""), 9.0)
