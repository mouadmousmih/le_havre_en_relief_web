"""
Transforme les segments de routes OSM en polygones Shapely prêts à extruder.
Gère la fusion des doubles voies (chaussées séparées) en une ligne médiane unique.
"""

from shapely.geometry import (
    LineString, Polygon, MultiPolygon, GeometryCollection, MultiLineString,
)
from shapely.ops import unary_union, linemerge, nearest_points
from shapely.validation import make_valid


class RoadProcessor:

    def __init__(
        self,
        width_mm:      float = 8.0,
        resolution:    int   = 4,
        allowed_types: list  = None,
        custom_widths: dict  = None,
        enable_fusion: bool  = True,
    ):
        self.width_mm      = width_mm
        self.resolution    = resolution
        self.allowed_types = set(allowed_types) if allowed_types else None
        self.enable_fusion = enable_fusion
        self.custom_widths = {k.lower(): v for k, v in (custom_widths or {}).items()}
        print(f"[RoadProcessor] Largeur standard : {width_mm}mm")


    def process_and_merge(self, roads: list, clip_bbox: dict = None) -> list:
        from shapely.geometry import box as sbox

        clip = None
        if clip_bbox:
            clip = sbox(clip_bbox["min_x"], clip_bbox["min_y"],
                        clip_bbox["max_x"], clip_bbox["max_y"])

        groups = {}
        for road in roads:
            if self.allowed_types and road.get("type", "unclassified") not in self.allowed_types:
                continue
            name = road.get("name", "").strip().lower() or f"unnamed_{road.get('id', '')}"
            groups.setdefault(name, []).append(road)

        polygons = []

        for name, road_list in groups.items():
            lines, road_types = [], []
            for r in road_list:
                coords = r.get("coordinates_mm", [])
                if len(coords) >= 2:
                    lines.append(LineString(coords))
                    road_types.append(r.get("type", "unclassified"))

            if not lines:
                continue

            main_type = road_types[0] if road_types else "unclassified"
            merged    = linemerge(lines)
            geoms     = [merged] if isinstance(merged, LineString) else list(merged.geoms)
            geoms     = [g for g in geoms if g.length > 2.0]
            is_dual   = False

            if (self.enable_fusion
                    and main_type not in ["service", "footway", "path", "cycleway"]
                    and len(geoms) > 1
                    and not name.startswith("unnamed_")):
                median_line = self._compute_centerline(geoms)
                if median_line:
                    geoms   = [median_line]
                    is_dual = True

            if name in self.custom_widths:
                w = self.custom_widths[name]
            elif is_dual:
                w = 16.0
            elif main_type in ["service", "footway", "path", "cycleway"]:
                w = 3.0
            else:
                w = self.width_mm

            half = w / 2.0

            for geom in geoms:
                poly = geom.buffer(half, cap_style=1, join_style=2, resolution=self.resolution)
                if clip is not None:
                    poly = poly.intersection(clip)
                if poly is not None and not poly.is_empty:
                    if not poly.is_valid:
                        poly = make_valid(poly)
                    polygons.extend(self._flatten(poly))

        final_union = unary_union(polygons)
        result      = self._flatten(final_union)
        print(f"[RoadProcessor] {len(result)} polygone(s) final(aux)")
        return result


    def _compute_centerline(self, lines: list):
        lines.sort(key=lambda x: x.length, reverse=True)
        ref_line    = lines[0]
        other_multi = MultiLineString(lines[1:])

        coords = []
        dists  = list(range(0, int(ref_line.length), 2))
        if ref_line.length not in dists:
            dists.append(ref_line.length)

        for d in dists:
            pt1 = ref_line.interpolate(d)
            pt2 = nearest_points(pt1, other_multi)[1]
            if pt1.distance(pt2) < 80.0:
                coords.append(((pt1.x + pt2.x) / 2.0, (pt1.y + pt2.y) / 2.0))
            else:
                coords.append((pt1.x, pt1.y))

        if len(coords) >= 2:
            return LineString(coords).simplify(1.0)
        return ref_line


    def _flatten(self, geom) -> list:
        if geom is None or geom.is_empty:
            return []
        if isinstance(geom, Polygon):
            return [geom]
        if isinstance(geom, MultiPolygon):
            return list(geom.geoms)
        if isinstance(geom, GeometryCollection):
            out = []
            for g in geom.geoms:
                out.extend(self._flatten(g))
            return out
        return []
