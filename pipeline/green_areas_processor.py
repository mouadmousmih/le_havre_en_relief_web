"""
Espaces verts en relief négatif : parcs et squares représentés par un creux
dans la plaque de base, distinguable au toucher des routes (bosses).
"""

import trimesh
from trimesh.creation import extrude_polygon
from shapely.geometry import box as sbox, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid


class GreenAreasProcessor:

    def __init__(self, depth_mm: float = 1.2):
        self.depth_mm = depth_mm
        print(f"[GreenAreas] Profondeur relief négatif : {depth_mm}mm")


    def process(self, green_areas: list, bbox_mm: dict) -> list:
        clip     = sbox(bbox_mm["min_x"], bbox_mm["min_y"],
                        bbox_mm["max_x"], bbox_mm["max_y"])
        polygons = []

        for area in green_areas:
            coords = area.get("coordinates_mm", [])
            if len(coords) < 3:
                continue
            try:
                poly = Polygon(coords)
                if not poly.is_valid:
                    poly = make_valid(poly)
                if poly is None or poly.is_empty:
                    continue
                clipped = poly.intersection(clip)
                if clipped is None or clipped.is_empty:
                    continue
                if not clipped.is_valid:
                    clipped = make_valid(clipped)
                polygons.extend(self._flatten(clipped))
            except Exception:
                continue

        print(f"[GreenAreas] {len(polygons)} espaces verts traités")
        return polygons


    def build_cutters(self, green_polygons: list, base_thickness: float, extra_height_mm: float = 50.0) -> list:
        total_height = self.depth_mm + extra_height_mm
        meshes = []
        for poly in green_polygons:
            if poly.area < 1.0:
                continue
            try:
                m = extrude_polygon(poly, height=total_height)
                m.apply_translation([0, 0, base_thickness - self.depth_mm])
                meshes.append(m)
            except Exception:
                continue
        print(f"[GreenAreas] {len(meshes)} cutters générés")
        return meshes


    def _flatten(self, geom) -> list:
        if isinstance(geom, Polygon):
            return [geom]
        if isinstance(geom, MultiPolygon):
            return list(geom.geoms)
        return []
