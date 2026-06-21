# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Le Havre en Relief** — a web app that generates tactile 3D maps (STL files) for 3D printing, designed for visually-impaired users. Users enter an address, choose a radius (100/200/500 m) and a relief variant; the server fetches OpenStreetMap data, builds a 3D mesh, and serves the result as a downloadable STL.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (Flask, port 5000, debug=True)
python app.py

# Production
gunicorn app:app --worker-class=gthread --workers=1 --threads=8 --timeout=300 --bind=0.0.0.0:$PORT
```

There are no tests and no linter configured.

## Architecture

### Stack
- **Backend:** Python/Flask, no build step
- **Frontend:** Vanilla JS + CSS, no bundler. Leaflet (CDN) for the map, Lucide (CDN) for icons
- **3D generation:** `trimesh` + `manifold3d` (Boolean ops) + `shapely` (2D geometry) + `pyproj` (CRS projection)

### Request Flow

```
Browser → GET /geocode?q=       → proxy to Nominatim, returns {lat, lon}
Browser → GET /generate?...     → Server-Sent Events stream (up to 300 s)
                                   ↓ pipeline runs server-side (5 steps below)
                                   ↓ SSE events: step1..step5, then "done" or "error"
Browser → GET /view/<uuid>.stl  → raw binary STL for in-browser viewer
Browser → GET /download/<uuid>.stl → STL as named file attachment
```

### 5-Step Generation Pipeline (`pipeline/`)

| Step | File | What it does |
|------|------|--------------|
| 1 | `app.py::compute_bbox` | lat/lon + radius → WGS84 bounding box |
| 2 | `pipeline/osm_fetcher.py` | Overpass API query — roads, buildings, green areas. Excludes `junction=roundabout`. |
| 3 | `pipeline/crs_converter.py` | WGS84 → Lambert 93 (EPSG:2154) → centred mm at 1:1000 |
| 4a | `pipeline/relief_positive.py` | **V1:** flat plate + extruded road polygons (2.5 mm bumps) |
| 4b | `pipeline/relief_positive_canal.py` | **V2:** plate with Boolean-carved channel grooves |
| 5 | `pipeline/green_areas_processor.py` | Boolean-difference subtraction of green area volumes |

Pipeline output → `trimesh.Trimesh` → binary STL → `outputs/<uuid>.stl`.

### Road Processing Key Patterns

- **Dual-carriageway fusion:** Roads sharing the same name are grouped and their centreline is computed by sampling at 2 mm intervals to prevent doubled bumps.
- **Service roads:** Always grouped by OSM ID (not name) to avoid polluting main road groups.
- **Roundabout exclusion:** OSM `junction=roundabout` filtered at fetch time; residual closed rings filtered via `geom.is_ring` in `RoadProcessor`.
- **Boolean engine:** All mesh union/difference ops use `manifold3d` (faster and more robust than trimesh's default BSP engine).

### 3D Viewer (`static/viewer.js`)

Pure vanilla WebGL — no Three.js, no Babylon.js. Implements:
- Binary STL parser
- Custom 4×4 matrix math (perspective + rotation)
- GLSL shaders with two-light Lambertian shading
- Mouse + touch controls (drag to rotate, scroll/pinch to zoom)

### Security Notes

- `/view/<id>` and `/download/<id>` routes validate that the filename is exactly a 32-character hex string before filesystem access.
- `outputs/` directory accumulates STL files indefinitely (no cleanup mechanism).
