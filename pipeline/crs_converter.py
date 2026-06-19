"""
Conversion de coordonnées WGS84 (lon/lat) vers Lambert 93 (mètres),
puis vers des millimètres centrés sur la bounding box de la zone.
"""

from pyproj import Transformer


class CRSConverter:

    def __init__(self, scale: int = 1000):
        self.scale       = scale
        self.transformer = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
        self.center      = None
        self.bbox_mm     = None
        print(f"[CRSConverter] Échelle 1:{scale}")


    def convert(self, roads: list, bbox_wgs84: list) -> list:
        lon_min, lat_min, lon_max, lat_max = bbox_wgs84
        cx, cy = self.transformer.transform(
            (lon_min + lon_max) / 2,
            (lat_min + lat_max) / 2,
        )
        self.center = (cx, cy)

        corners_mm = [
            self._to_mm(*self.transformer.transform(lon_min, lat_min)),
            self._to_mm(*self.transformer.transform(lon_max, lat_min)),
            self._to_mm(*self.transformer.transform(lon_max, lat_max)),
            self._to_mm(*self.transformer.transform(lon_min, lat_max)),
        ]
        xs = [c[0] for c in corners_mm]
        ys = [c[1] for c in corners_mm]
        self.bbox_mm = {
            "min_x": min(xs), "max_x": max(xs),
            "min_y": min(ys), "max_y": max(ys),
            "width": max(xs) - min(xs),
            "height": max(ys) - min(ys),
        }

        print(f"[CRSConverter] Maquette : "
              f"{self.bbox_mm['width']:.1f} x {self.bbox_mm['height']:.1f} mm")

        for road in roads:
            coords_lambert = [
                self.transformer.transform(c[0], c[1])
                for c in road["coordinates"]
            ]
            road["coordinates_mm"] = [
                list(self._to_mm(x, y)) for x, y in coords_lambert
            ]
        return roads


    def convert_green_areas(self, green_areas: list, include_ids: list = None) -> list:
        if self.center is None:
            raise RuntimeError("Appelle convert() avant convert_green_areas()")

        id_filter = None
        if include_ids:
            try:
                id_filter = set(int(i) for i in include_ids)
            except (ValueError, TypeError):
                pass

        out = []
        for area in green_areas:
            if id_filter is not None:
                try:
                    area_id = int(area.get("id", -1))
                except (ValueError, TypeError):
                    area_id = -1
                if area_id not in id_filter:
                    continue

            coords = area.get("coordinates", [])
            if len(coords) < 3:
                continue
            try:
                coords_mm = []
                for lon, lat in coords:
                    x, y = self.transformer.transform(lon, lat)
                    coords_mm.append(list(self._to_mm(x, y)))
                na = dict(area)
                na["coordinates_mm"] = coords_mm
                out.append(na)
            except Exception:
                continue

        print(f"[CRSConverter] {len(out)} espaces verts projetés")
        return out


    def _to_mm(self, x: float, y: float) -> tuple:
        cx, cy = self.center
        return (x - cx) * 1000 / self.scale, (y - cy) * 1000 / self.scale
