import numpy as np
import trimesh
from trimesh.creation import extrude_polygon, cylinder as make_cylinder, icosphere
from trimesh import transformations as tf
from shapely.validation import make_valid
from shapely.geometry import (
    box as sbox, Polygon, MultiPolygon,
    LineString, MultiLineString, Point,
)
from shapely.ops import linemerge, nearest_points, unary_union


class ReliefPositiveCanal:

    def __init__(
        self,
        base_thickness: float = 2.5,
        wall_height:    float = 2.5,
        wall_thickness: float = 1.5,
        canal_width:    float = 5.0,
        margin:         float = 5.0,
        resolution:     int   = 32,
        allowed_types:  list  = None,
        custom_widths:  dict  = None,
        enable_fusion:  bool  = True,
    ):
        self.base_thickness = base_thickness
        self.wall_height    = wall_height
        self.wall_thickness = wall_thickness
        self.default_width  = canal_width + 2 * wall_thickness
        self.margin         = margin
        self.resolution     = resolution
        self.allowed_types  = set(allowed_types) if allowed_types else None
        self.enable_fusion  = enable_fusion
        self.custom_widths  = {k.lower(): v for k, v in (custom_widths or {}).items()}

    def build(self, roads: list, bbox_mm: dict, green_cutters: list = None) -> trimesh.Trimesh:
        clip = sbox(bbox_mm["min_x"], bbox_mm["min_y"],
                    bbox_mm["max_x"], bbox_mm["max_y"])

        w     = bbox_mm["width"]  + 2 * self.margin
        h     = bbox_mm["height"] + 2 * self.margin
        plate = trimesh.creation.box(extents=[w, h, self.base_thickness])
        plate.apply_translation([0, 0, self.base_thickness / 2])

        groups = {}
        for road in roads:
            if not isinstance(road, dict):
                continue
            r_type = road.get("type", "unclassified")
            if self.allowed_types and r_type not in self.allowed_types:
                continue
            name = road.get("name", "").strip().lower()
            if not name:
                name = f"unnamed_{road.get('id', '')}"
            groups.setdefault(name, []).append(road)

        processed_data = []
        centerlines    = []

        for name, road_list in groups.items():
            lines      = []
            road_types = []
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

            is_dual = False

            if (self.enable_fusion
                    and main_type not in ["service", "footway", "path", "cycleway"]
                    and len(geoms) > 1
                    and not name.startswith("unnamed_")):
                median_line = self._compute_centerline(geoms)
                if median_line:
                    geoms   = [median_line]
                    is_dual = True
                    centerlines.extend(geoms)

            if name in self.custom_widths:
                total_w = self.custom_widths[name]
            elif is_dual:
                total_w = 16.0
            elif main_type in ["service", "footway", "path", "cycleway"]:
                total_w = 3.0
            else:
                total_w = self.default_width

            c_width = max(0.1, total_w - 2 * self.wall_thickness)

            processed_data.append({
                "geoms"   : geoms,
                "total_w" : total_w,
                "c_width" : c_width,
            })

        if centerlines:
            center_union = unary_union(centerlines)
            for data in processed_data:
                new_geoms = []
                for geom in data["geoms"]:
                    if isinstance(geom, LineString) and len(geom.coords) >= 2:
                        coords  = list(geom.coords)
                        p_start = Point(coords[0])
                        p_end   = Point(coords[-1])

                        if 0.1 < p_start.distance(center_union) <= 50.0:
                            n_pt = nearest_points(p_start, center_union)[1]
                            coords.insert(0, (n_pt.x, n_pt.y))

                        if 0.1 < p_end.distance(center_union) <= 50.0:
                            n_pt = nearest_points(p_end, center_union)[1]
                            coords.append((n_pt.x, n_pt.y))

                        new_geoms.append(LineString(coords))
                    else:
                        new_geoms.append(geom)
                data["geoms"] = new_geoms

        blocks    = []
        cylinders = []

        for data in processed_data:
            total_w = data["total_w"]
            c_width = data["c_width"]

            for geom in data["geoms"]:
                poly         = geom.buffer(total_w / 2.0, cap_style=2, join_style=2)
                poly_clipped = poly.intersection(clip)
                if poly_clipped and not poly_clipped.is_empty:
                    if not poly_clipped.is_valid:
                        poly_clipped = make_valid(poly_clipped)
                    for sub in self._flatten(poly_clipped):
                        if sub.area > 0.1:
                            block = extrude_polygon(sub, height=self.wall_height)
                            block.apply_translation([0, 0, self.base_thickness])
                            blocks.append(block)

                line_clipped = geom.intersection(clip)
                for sub_line in self._extract_lines(line_clipped):
                    co = list(sub_line.coords)
                    if len(co) < 2:
                        continue
                    cylinders.append(self._joint_sphere(co[0],  c_width))
                    cylinders.append(self._joint_sphere(co[-1], c_width))
                    for i in range(len(co) - 1):
                        cyl = self._segment_cylinder(co[i], co[i + 1], c_width)
                        if cyl:
                            cylinders.append(cyl)

        if not blocks:
            return plate

        roads_union = self._safe_union(blocks)

        carved = roads_union
        if cylinders:
            cyl_union = self._safe_union(cylinders)
            try:
                carved = trimesh.boolean.difference(
                    [roads_union, cyl_union], engine="manifold"
                )
            except Exception:
                carved = roads_union

        combined = trimesh.util.concatenate([plate, carved])

        if green_cutters:
            try:
                cutter_union = trimesh.boolean.union(green_cutters, engine="manifold")
                combined = trimesh.boolean.difference(
                    [combined, cutter_union], engine="manifold"
                )
            except Exception:
                pass

        return combined

    def _joint_sphere(self, p: tuple, c_width: float) -> trimesh.Trimesh:
        r      = c_width / 2.0
        sphere = icosphere(radius=r, subdivisions=3)
        if abs(r - self.wall_height) > 0.01:
            scale_z        = np.eye(4)
            scale_z[2, 2]  = self.wall_height / r
            sphere.apply_transform(scale_z)
        sphere.apply_translation([p[0], p[1], self.base_thickness + self.wall_height])
        return sphere

    def _segment_cylinder(self, p0: tuple, p1: tuple, c_width: float):
        x0, y0 = p0[0], p0[1]
        x1, y1 = p1[0], p1[1]
        dx, dy = x1 - x0, y1 - y0
        length = np.hypot(dx, dy)
        if length < 0.01:
            return None
        r   = c_width / 2.0
        cyl = make_cylinder(radius=r, height=length + 1.0, sections=self.resolution)
        cyl.apply_transform(tf.rotation_matrix(np.pi / 2, [0, 1, 0]))
        cyl.apply_transform(tf.rotation_matrix(np.arctan2(dy, dx), [0, 0, 1]))
        if abs(r - self.wall_height) > 0.01:
            scale_z       = np.eye(4)
            scale_z[2, 2] = self.wall_height / r
            cyl.apply_transform(scale_z)
        cyl.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2,
                                self.base_thickness + self.wall_height])
        return cyl

    def _compute_centerline(self, lines: list) -> LineString:
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

    def _extract_lines(self, geom) -> list:
        if geom is None or geom.is_empty:
            return []
        if geom.geom_type == "LineString":
            return [geom]
        if geom.geom_type in ("MultiLineString", "GeometryCollection"):
            return [g for g in geom.geoms if g.geom_type == "LineString"]
        return []

    def _safe_union(self, meshes: list) -> trimesh.Trimesh:
        if len(meshes) == 1:
            return meshes[0]
        try:
            return trimesh.boolean.union(meshes, engine="manifold")
        except Exception:
            return trimesh.util.concatenate(meshes)

    def _flatten(self, geom) -> list:
        if isinstance(geom, Polygon):
            return [geom]
        if isinstance(geom, MultiPolygon):
            return list(geom.geoms)
        return []
