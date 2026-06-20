"""
app.py — Backend Flask pour la génération de maquettes tactiles en relief positif.

Routes :
    GET  /             → page principale
    GET  /geocode?q=   → traduit une adresse en {lat, lon} via Nominatim
    GET  /generate?lat=&lon=&radius=  → pipeline + progression SSE
    GET  /download/<uuid>.stl         → téléchargement du fichier généré
"""

import json
import math
import uuid
import os
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

from flask import Flask, render_template, request, Response, send_file, jsonify

from pipeline.osm_fetcher          import OSMFetcher
from pipeline.crs_converter        import CRSConverter
from pipeline.road_processor       import RoadProcessor
from pipeline.relief_positive      import ReliefPositive
from pipeline.green_areas_processor import GreenAreasProcessor

# ── App ──
app = Flask(__name__)

OUTPUTS_DIR   = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

ROAD_TYPES = [
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "residential",
]


# ── Helpers ──

def sse(event_type: str, **data) -> str:
    """Formate un événement Server-Sent Event."""
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


def compute_bbox(lat: float, lon: float, radius_m: int) -> list:
    """
    Bounding box [lon_min, lat_min, lon_max, lat_max] autour d'un point.
    Utilise une approximation équirectangulaire — précise pour de petits rayons.
    """
    delta_lat = radius_m / 111_320.0
    delta_lon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return [
        lon - delta_lon, lat - delta_lat,
        lon + delta_lon, lat + delta_lat,
    ]


# ── Routes ──

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/geocode")
def geocode():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"found": False, "error": "Adresse vide"})

    url = NOMINATIM_URL + "?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "tactile-map-web/1.0 (mmousmih@gmail.com)"})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        if not data:
            return jsonify({"found": False, "error": "Adresse introuvable"})
        r = data[0]
        return jsonify({
            "found"        : True,
            "lat"          : float(r["lat"]),
            "lon"          : float(r["lon"]),
            "display_name" : r.get("display_name", ""),
        })
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return jsonify({"found": False, "error": "Trop de requêtes — réessaie dans quelques secondes."})
        return jsonify({"found": False, "error": f"Erreur HTTP {e.code}"})
    except Exception as e:
        return jsonify({"found": False, "error": str(e)})


@app.route("/generate")
def generate():
    try:
        lat    = float(request.args["lat"])
        lon    = float(request.args["lon"])
        radius = int(request.args.get("radius", 200))
    except (KeyError, ValueError):
        return jsonify({"error": "Paramètres invalides"}), 400

    def stream():
        try:
            # 1 ── Calcul de la zone
            yield sse("progress", step=1, total=5, msg="Calcul de la zone...")
            bbox = compute_bbox(lat, lon, radius)

            # 2 ── Téléchargement OSM
            yield sse("progress", step=2, total=5, msg="Téléchargement des données OSM...")
            fetcher = OSMFetcher()
            roads, _, green_areas = fetcher.fetch(
                bbox, leisure_types=["park", "garden", "square"]
            )
            if not roads:
                yield sse("error", msg="Aucune route trouvée dans cette zone.")
                return

            # 3 ── Projection des coordonnées
            yield sse("progress", step=3, total=5, msg="Projection des coordonnées...")
            converter  = CRSConverter(scale=1000)
            roads_proj = converter.convert(roads, bbox)
            bbox_mm    = converter.bbox_mm

            green_proj = []
            if green_areas:
                green_proj = converter.convert_green_areas(green_areas, include_ids=None)

            # 4 ── Traitement des routes
            yield sse("progress", step=4, total=5, msg="Traitement des routes...")
            processor  = RoadProcessor(
                width_mm      = 8.0,
                resolution    = 4,
                allowed_types = ROAD_TYPES,
                enable_fusion = True,
            )
            road_polys = processor.process_and_merge(roads_proj, clip_bbox=bbox_mm)

            green_cutters = []
            if green_proj:
                gap           = GreenAreasProcessor(depth_mm=1.2)
                green_polys   = gap.process(green_proj, bbox_mm)
                green_cutters = gap.build_cutters(green_polys, base_thickness=2.5)

            # 5 ── Génération du maillage
            yield sse("progress", step=5, total=5, msg="Génération du maillage 3D...")
            mesh = ReliefPositive(
                base_thickness = 2.5,
                road_height    = 2.5,
                margin         = 5.0,
            ).build(road_polys, bbox_mm, green_cutters=green_cutters)

            filename = f"{uuid.uuid4().hex}.stl"
            out_path = OUTPUTS_DIR / filename
            mesh.export(str(out_path), file_type="stl")

            size_kb = round(out_path.stat().st_size / 1024)
            w_mm    = round(bbox_mm["width"]  + 10)
            h_mm    = round(bbox_mm["height"] + 10)

            yield sse("done",
                      msg     = "Maquette générée !",
                      file    = filename,
                      size_kb = size_kb,
                      dims    = f"{w_mm} × {h_mm} mm")

        except Exception as e:
            yield sse("error", msg=str(e))

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/view/<filename>")
def view_stl(filename):
    """Sert le STL sans en-tête attachment — pour le chargement Three.js."""
    name = filename.removesuffix(".stl")
    if not (len(name) == 32 and all(c in "0123456789abcdef" for c in name)):
        return "Nom de fichier invalide", 400
    path = OUTPUTS_DIR / filename
    if not path.exists():
        return "Fichier introuvable", 404
    return send_file(str(path), mimetype="application/octet-stream")


@app.route("/download/<filename>")
def download(filename):
    # Sécurité : on n'accepte que les noms au format UUID hex + .stl
    name = filename.removesuffix(".stl")
    if not (len(name) == 32 and all(c in "0123456789abcdef" for c in name)):
        return "Nom de fichier invalide", 400
    path = OUTPUTS_DIR / filename
    if not path.exists():
        return "Fichier introuvable", 404
    return send_file(str(path), as_attachment=True, download_name="maquette_tactile.stl")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(debug=debug, threaded=True, host="0.0.0.0", port=port)
