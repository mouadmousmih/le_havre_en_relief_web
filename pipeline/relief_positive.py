"""
Variante V1 : routes en relief positif (bosses) sur plaque de base.
Les espaces verts sont creusés en relief négatif par soustraction booléenne.
"""

import trimesh
from trimesh.creation import extrude_polygon
from shapely.validation import make_valid
from shapely.geometry import box as sbox, Polygon, MultiPolygon


class ReliefPositive:

    def __init__(
        self,
        base_thickness: float = 2.5,
        road_height:    float = 2.5,
        margin:         float = 5.0,
    ):
        self.base_thickness = base_thickness
        self.road_height    = road_height
        self.margin         = margin
        print(f"[ReliefPositive] base={base_thickness}mm  relief={road_height}mm  marge={margin}mm")


    def build(self, road_polygons: list, bbox_mm: dict, green_cutters: list = None) -> trimesh.Trimesh:
        m = self.margin
        w     = bbox_mm["width"]  + 2 * m
        h     = bbox_mm["height"] + 2 * m
        plate = trimesh.creation.box(extents=[w, h, self.base_thickness])
        plate.apply_translation([0, 0, self.base_thickness / 2])

        meshes = [plate]
        clip   = sbox(bbox_mm["min_x"], bbox_mm["min_y"],
                      bbox_mm["max_x"], bbox_mm["max_y"])

        count, errors = 0, 0
        for poly in road_polygons:
            try:
                clipped = poly.intersection(clip)
                if clipped is None or clipped.is_empty:
                    continue
                if not clipped.is_valid:
                    clipped = make_valid(clipped)
                for sub in self._flatten(clipped):
                    if sub.area < 0.01:
                        continue
                    mesh = extrude_polygon(sub, height=self.road_height)
                    mesh.apply_translation([0, 0, self.base_thickness])
                    meshes.append(mesh)
                    count += 1
            except Exception:
                errors += 1

        print(f"[ReliefPositive] {count} meshes de routes"
              + (f"  ({errors} erreurs)" if errors else ""))

        combined = trimesh.util.concatenate(meshes)

        if green_cutters:
            print(f"[ReliefPositive] Soustraction de {len(green_cutters)} espaces verts...")
            try:
                cutter_union = trimesh.boolean.union(green_cutters, engine="manifold")
                combined = trimesh.boolean.difference(
                    [combined, cutter_union], engine="manifold"
                )
            except Exception as e:
                print(f"[ReliefPositive] Soustraction échouée : {e}")

        d = combined.bounds[1] - combined.bounds[0]
        print(f"[ReliefPositive] {d[0]:.1f}x{d[1]:.1f}x{d[2]:.1f}mm  "
              f"faces={len(combined.faces):,}  watertight={combined.is_watertight}")
        return combined


    def _flatten(self, geom) -> list:
        if isinstance(geom, Polygon):
            return [geom]
        if isinstance(geom, MultiPolygon):
            return list(geom.geoms)
        return []
