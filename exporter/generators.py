#Author: Fusion2SCAD
#Description: OpenSCAD/BOSL2 code generation functions

import sys
import os
import math

from .utils import CM_TO_MM, format_value, WarningsCollector

# Try to import profile_utils
try:
    script_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if script_dir not in sys.path:
        sys.path.append(script_dir)
    from profile_utils import (
        extract_profile_polygon,
        format_polygon_scad,
        format_polygon_with_holes_scad
    )
    PROFILE_UTILS_AVAILABLE = True
except ImportError:
    PROFILE_UTILS_AVAILABLE = False

def calculate_hole_center_radius(hole_points: list) -> tuple:
    """Calculate center and radius of a circular hole from its points.

    Args:
        hole_points: List of (x, y) tuples defining the hole polygon

    Returns:
        Tuple of ((cx, cy), radius) or None if not a valid circle
    """
    if not hole_points or len(hole_points) < 3:
        return None

    # Calculate centroid as center
    xs = [p[0] for p in hole_points]
    ys = [p[1] for p in hole_points]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)

    # Calculate average radius
    radii = [math.sqrt((p[0] - cx)**2 + (p[1] - cy)**2) for p in hole_points]
    avg_radius = sum(radii) / len(radii)

    # Check if it's actually circular (all radii similar)
    radius_variance = max(radii) - min(radii)
    if radius_variance > avg_radius * 0.1:  # More than 10% variance = not circular
        return None

    return ((cx, cy), avg_radius)


def generate_hole_cut(hole_points: list, height: str, indent: str) -> list:
    """Generate SCAD code to cut out a hole from a solid.

    Args:
        hole_points: List of (x, y) tuples defining the hole
        height: The extrusion height as a formatted string
        indent: Current indentation string

    Returns:
        List of SCAD code lines for the hole cut
    """
    lines = []

    # Try to detect if it's a circular hole
    circle_info = calculate_hole_center_radius(hole_points)

    if circle_info:
        (cx, cy), radius = circle_info
        # Use cylinder for circular holes (cleaner output)
        lines.append(f"{indent}translate([{format_value(cx)}, {format_value(cy)}, -1])")
        lines.append(f"{indent}    cyl(h={height}+2, r={format_value(radius)}, anchor=BOTTOM);")
    else:
        # Use linear_extrude for non-circular holes
        formatted_pts = []
        for x, y in hole_points:
            fx = f"{x:.4f}".rstrip('0').rstrip('.')
            fy = f"{y:.4f}".rstrip('0').rstrip('.')
            formatted_pts.append(f"[{fx}, {fy}]")
        points_str = ", ".join(formatted_pts)
        lines.append(f"{indent}translate([0, 0, -1])")
        lines.append(f"{indent}    linear_extrude(height={height}+2)")
        lines.append(f"{indent}        polygon(points=[{points_str}]);")

    return lines


def calculate_max_inset(points: list) -> float:
    """Calculate the maximum safe inset radius for a polygon path.

    This prevents offset_sweep from creating degenerate geometry when
    the rounding radius is too large for the profile.

    Args:
        points: List of (x, y) tuples defining the polygon path

    Returns:
        Maximum safe inset radius (conservative estimate), or 0 if path is unsuitable
    """
    if not points or len(points) < 3:
        return 0

    # Paths with only 3 points form very thin triangles that often fail with offset_sweep
    # Require at least 4 points for offset_sweep to work reliably
    if len(points) < 4:
        return 0

    # Calculate bounding box
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)

    # Check for degenerate (very thin) profiles - aspect ratio > 10:1
    if width > 0 and height > 0:
        aspect_ratio = max(width, height) / min(width, height)
        if aspect_ratio > 10:
            # Very thin profile - skip rounding
            return 0

    # Calculate minimum distance from each vertex to all non-adjacent edges
    # This gives a better estimate of the narrowest part of the polygon
    min_vertex_clearance = float('inf')
    n = len(points)

    for i in range(n):
        px, py = points[i]
        # Check distance to all non-adjacent edges
        for j in range(n):
            # Skip adjacent edges (j, j+1) where j is i-1 or i
            next_j = (j + 1) % n
            if j == i or next_j == i or j == (i - 1) % n:
                continue

            # Calculate distance from point i to edge j->j+1
            x1, y1 = points[j]
            x2, y2 = points[next_j]

            # Edge vector
            edge_dx = x2 - x1
            edge_dy = y2 - y1
            edge_len_sq = edge_dx * edge_dx + edge_dy * edge_dy

            if edge_len_sq < 1e-10:
                continue

            # Project point onto edge line
            t = max(0, min(1, ((px - x1) * edge_dx + (py - y1) * edge_dy) / edge_len_sq))

            # Closest point on edge segment
            closest_x = x1 + t * edge_dx
            closest_y = y1 + t * edge_dy

            # Distance from vertex to closest point on edge
            dist = math.sqrt((px - closest_x)**2 + (py - closest_y)**2)
            min_vertex_clearance = min(min_vertex_clearance, dist)

    # Also consider minimum edge-to-edge width (perpendicular distance)
    min_dim = min(width, height)

    # Use the most conservative estimate
    if min_vertex_clearance < float('inf') and min_vertex_clearance < min_dim:
        # Use vertex clearance but apply strong safety factor
        max_inset = min_vertex_clearance * 0.4
    else:
        # Fall back to bounding box approach with safety factor
        max_inset = (min_dim / 2) * 0.7

    # Additional safety: never allow inset larger than 1/3 of smallest bounding box dimension
    absolute_max = min_dim / 3

    return min(max_inset, absolute_max)


def generate_header() -> list:
    """Generate the OpenSCAD file header with BOSL2 include"""
    return [
        "// Generated by Fusion2SCAD",
        "// https://github.com/BelfrySCAD/BOSL2",
        "",
        "include <BOSL2/std.scad>",
        "include <BOSL2/rounding.scad>",
        "",
        "// Set default fragment count for smooth curves",
        "$fn = 32;",
        "",
        "// ============================================",
        "// Parameters (exported from Fusion 360)",
        "// ============================================",
        ""
    ]


def generate_parameters_section(parameters: dict) -> list:
    """Generate OpenSCAD variable declarations from Fusion parameters"""
    lines = []
    for orig_name, param_info in parameters.items():
        comment = f"  // {param_info['comment']}" if param_info['comment'] else ""
        lines.append(f"{param_info['name']} = {format_value(param_info['value'])};{comment}")
    if lines:
        lines.append("")
    return lines


def generate_transform_prefix(feature_info: dict, profile_center: tuple) -> tuple:
    """Generate multmatrix transform for proper 3D positioning using sketch transform.

    Returns:
        Tuple of (lines, indent_string)
    """
    lines = []
    indent = ""
    cx, cy = profile_center

    sketch_transform = feature_info.get('sketch_transform')

    if sketch_transform:
        ox, oy, oz = sketch_transform['origin']
        xx, xy, xz = sketch_transform['x_axis']
        yx, yy, yz = sketch_transform['y_axis']
        zx, zy, zz = sketch_transform['z_axis']

        ox, oy, oz = ox * CM_TO_MM, oy * CM_TO_MM, oz * CM_TO_MM

        tx = ox + xx * cx + yx * cy
        ty = oy + xy * cx + yy * cy
        tz = oz + xz * cx + yz * cy

        matrix = [
            [xx, yx, zx, tx],
            [xy, yy, zy, ty],
            [xz, yz, zz, tz],
            [0, 0, 0, 1]
        ]

        matrix_str = "[\n"
        for row in matrix:
            row_str = ", ".join(format_value(v) for v in row)
            matrix_str += f"        [{row_str}],\n"
        matrix_str = matrix_str.rstrip(",\n") + "\n    ]"

        lines.append(f"multmatrix({matrix_str})")
        indent = "    "
    else:
        plane_origin = feature_info.get('plane_origin', (0, 0, 0))
        rotation = feature_info.get('rotation')
        ox, oy, oz = plane_origin

        if rotation and rotation != (0, 0, 0):
            rx, ry, rz = rotation
            if ox != 0 or oy != 0 or oz != 0:
                lines.append(f"translate([{format_value(ox)}, {format_value(oy)}, {format_value(oz)}])")
                indent = "    "
            lines.append(f"{indent}rotate([{format_value(rx)}, {format_value(ry)}, {format_value(rz)}])")
            indent += "    "
            if cx != 0 or cy != 0:
                lines.append(f"{indent}translate([{format_value(cx)}, {format_value(cy)}, 0])")
                indent += "    "
        else:
            total_x = ox + cx
            total_y = oy + cy
            total_z = oz
            if total_x != 0 or total_y != 0 or total_z != 0:
                lines.append(f"translate([{format_value(total_x)}, {format_value(total_y)}, {format_value(total_z)}])")
                indent = "    "

    return lines, indent


def format_edges_param(edge_types: set) -> str:
    """Format edge types into BOSL2 edges parameter.

    Args:
        edge_types: Set containing 'Z', 'TOP', 'BOTTOM'

    Returns:
        String like '"Z"', 'TOP', '[TOP, BOTTOM]', '["Z", TOP]', etc.
    """
    if not edge_types:
        return None

    # Convert set to sorted list for consistent output
    edges = []
    if 'Z' in edge_types:
        edges.append('"Z"')
    if 'TOP' in edge_types:
        edges.append('TOP')
    if 'BOTTOM' in edge_types:
        edges.append('BOTTOM')

    if len(edges) == 1:
        return edges[0]
    else:
        return f"[{', '.join(edges)}]"


def generate_extrude_scad(feature_info: dict, feature_name: str,
                          rounding: float = None, chamfer: float = None,
                          rounding_edges: set = None, chamfer_edges: set = None,
                          warnings: WarningsCollector = None) -> list:
    """Generate BOSL2 code for an extrusion with optional rounding/chamfer.

    Args:
        feature_info: Feature analysis data
        feature_name: Name of the feature for comments
        rounding: Fillet radius (mm)
        chamfer: Chamfer distance (mm)
        rounding_edges: Set of edge types for rounding ('Z', 'TOP', 'BOTTOM')
        chamfer_edges: Set of edge types for chamfer ('Z', 'TOP', 'BOTTOM')
        warnings: Optional WarningsCollector for consolidated reporting
    """
    lines = []
    raw_height = feature_info.get('height')

    # Check for missing height (e.g., ToEntity extents that couldn't be resolved)
    if raw_height is None:
        raise ValueError(f"height could not be determined (extent type may be 'To Object' which is not fully supported)")

    height = format_value(raw_height)
    # For cuboid/cyl, we need absolute height (BOSL2 doesn't accept negative sizes)
    abs_height = format_value(abs(raw_height))
    # When height is negative, use TOP anchor so geometry extends in correct direction
    anchor = "TOP" if raw_height < 0 else "BOTTOM"

    # Default to empty sets if None
    if rounding_edges is None:
        rounding_edges = set()
    if chamfer_edges is None:
        chamfer_edges = set()

    for profile in feature_info['profiles']:
        lines.append(f"// {feature_name} (plane: {feature_info.get('sketch_plane', 'XY')})")

        if profile['is_circle']:
            radius = format_value(profile['radius'])
            cx, cy = profile['center']

            cyl_params = [f"h={abs_height}", f"r={radius}"]
            # For cylinders, use rounding1/rounding2 for selective edges
            # Clamp rounding to fit within height
            height_val = abs(raw_height)

            has_rounding = rounding and rounding > 0
            has_chamfer = chamfer and chamfer > 0

            # Track which edges get rounding (to avoid chamfer conflict)
            rounding_applied_top = False
            rounding_applied_bottom = False

            if has_rounding:
                # Determine max rounding based on which edges are affected
                both_ends = ('TOP' in rounding_edges and 'BOTTOM' in rounding_edges) or not rounding_edges
                max_rounding = (height_val / 2 * 0.95) if both_ends else (height_val * 0.95)
                effective_rounding = min(rounding, max_rounding)
                if effective_rounding < rounding and warnings:
                    warnings.add_warning(
                        feature_name,
                        f"rounding reduced {format_value(rounding)}->{format_value(effective_rounding)}mm (height constraint)",
                        "constraint"
                    )
                if 'TOP' in rounding_edges and 'BOTTOM' in rounding_edges:
                    cyl_params.append(f"rounding={format_value(effective_rounding)}")
                    rounding_applied_top = rounding_applied_bottom = True
                elif 'TOP' in rounding_edges:
                    cyl_params.append(f"rounding2={format_value(effective_rounding)}")
                    rounding_applied_top = True
                elif 'BOTTOM' in rounding_edges:
                    cyl_params.append(f"rounding1={format_value(effective_rounding)}")
                    rounding_applied_bottom = True
                elif not rounding_edges:
                    # No edge info, apply to all (fallback)
                    cyl_params.append(f"rounding={format_value(effective_rounding)}")
                    rounding_applied_top = rounding_applied_bottom = True

            if has_chamfer:
                # BOSL2 cyl doesn't support rounding and chamfer on the same edge
                # Only apply chamfer to edges that don't have rounding
                both_ends_chamfer = ('TOP' in chamfer_edges and 'BOTTOM' in chamfer_edges) or not chamfer_edges
                max_chamfer = (height_val / 2 * 0.95) if both_ends_chamfer else (height_val * 0.95)
                effective_chamfer = min(chamfer, max_chamfer)
                if effective_chamfer < chamfer and warnings:
                    warnings.add_warning(
                        feature_name,
                        f"chamfer reduced {format_value(chamfer)}->{format_value(effective_chamfer)}mm (height constraint)",
                        "constraint"
                    )

                # Determine which edges can get chamfer (no rounding conflict)
                chamfer_top = ('TOP' in chamfer_edges or not chamfer_edges) and not rounding_applied_top
                chamfer_bottom = ('BOTTOM' in chamfer_edges or not chamfer_edges) and not rounding_applied_bottom

                if chamfer_top and chamfer_bottom:
                    cyl_params.append(f"chamfer={format_value(effective_chamfer)}")
                elif chamfer_top:
                    cyl_params.append(f"chamfer2={format_value(effective_chamfer)}")
                elif chamfer_bottom:
                    cyl_params.append(f"chamfer1={format_value(effective_chamfer)}")
                elif has_rounding and warnings:
                    # Chamfer requested but all edges already have rounding
                    warnings.add_warning(
                        feature_name,
                        f"chamfer skipped (BOSL2 cyl doesn't support both rounding and chamfer on same edge)",
                        "constraint"
                    )
            cyl_params.append(f"anchor={anchor}")
            cyl_call = f"cyl({', '.join(cyl_params)});"

            transform_lines, indent = generate_transform_prefix(feature_info, (cx, cy))
            lines.extend(transform_lines)
            lines.append(f"{indent}{cyl_call}")

        elif profile.get('is_rounded_rect'):
            width_val = profile['bbox']['width']
            depth_val = profile['bbox']['height']
            height_val = abs(raw_height)
            sketch_rounding_val = profile['rounding']
            cx, cy = profile['center']

            # Clamp sketch rounding to fit cuboid dimensions
            # BOSL2 requires rounding < min(width, depth, height) / 2
            min_dim = min(width_val, depth_val, height_val)
            max_rounding = min_dim / 2 * 0.95
            effective_sketch_rounding = min(sketch_rounding_val, max_rounding)
            if effective_sketch_rounding < sketch_rounding_val and warnings:
                warnings.add_warning(
                    feature_name,
                    f"sketch rounding reduced {format_value(sketch_rounding_val)}->{format_value(effective_sketch_rounding)}mm (cuboid size constraint)",
                    "constraint"
                )

            width = format_value(width_val)
            depth = format_value(depth_val)
            cuboid_params = [f"[{width}, {depth}, {abs_height}]"]
            cuboid_params.append(f"rounding={format_value(effective_sketch_rounding)}")

            # Combine sketch rounding edges ("Z") with any fillet edges
            combined_edges = {'Z'}  # Sketch rounding always applies to Z edges
            if rounding and rounding > 0:
                combined_edges.update(rounding_edges)
            edges_param = format_edges_param(combined_edges)
            if edges_param:
                cuboid_params.append(f"edges={edges_param}")

            # Note: BOSL2 cuboid doesn't support both rounding and chamfer
            # Since we already have sketch rounding, skip chamfer and warn
            if chamfer and chamfer > 0 and warnings:
                warnings.add_warning(
                    feature_name,
                    f"chamfer skipped (BOSL2 cuboid doesn't support both rounding and chamfer)",
                    "constraint"
                )
            cuboid_params.append(f"anchor={anchor}")
            cuboid_call = f"cuboid({', '.join(cuboid_params)});"

            transform_lines, indent = generate_transform_prefix(feature_info, (cx, cy))
            lines.extend(transform_lines)
            lines.append(f"{indent}{cuboid_call}")

        elif profile['is_rectangle']:
            width_val = profile['bbox']['width']
            depth_val = profile['bbox']['height']
            height_val = abs(raw_height)
            cx, cy = profile['center']

            # Calculate max rounding/chamfer for this cuboid
            min_dim = min(width_val, depth_val, height_val)
            max_edge_treatment = min_dim / 2 * 0.95

            width = format_value(width_val)
            depth = format_value(depth_val)
            cuboid_params = [f"[{width}, {depth}, {abs_height}]"]

            # BOSL2 cuboid doesn't support both rounding and chamfer
            # Prioritize rounding over chamfer if both are specified
            has_rounding = rounding and rounding > 0
            has_chamfer = chamfer and chamfer > 0

            if has_rounding:
                effective_rounding = min(rounding, max_edge_treatment)
                if effective_rounding < rounding and warnings:
                    warnings.add_warning(
                        feature_name,
                        f"rounding reduced {format_value(rounding)}->{format_value(effective_rounding)}mm (cuboid size constraint)",
                        "constraint"
                    )
                cuboid_params.append(f"rounding={format_value(effective_rounding)}")
                edges_param = format_edges_param(rounding_edges)
                if edges_param:
                    cuboid_params.append(f"edges={edges_param}")
                # Warn if chamfer was also requested but skipped
                if has_chamfer and warnings:
                    warnings.add_warning(
                        feature_name,
                        f"chamfer skipped (BOSL2 cuboid doesn't support both rounding and chamfer)",
                        "constraint"
                    )
            elif has_chamfer:
                effective_chamfer = min(chamfer, max_edge_treatment)
                if effective_chamfer < chamfer and warnings:
                    warnings.add_warning(
                        feature_name,
                        f"chamfer reduced {format_value(chamfer)}->{format_value(effective_chamfer)}mm (cuboid size constraint)",
                        "constraint"
                    )
                cuboid_params.append(f"chamfer={format_value(effective_chamfer)}")
                if chamfer_edges:
                    edges_param = format_edges_param(chamfer_edges)
                    if edges_param:
                        cuboid_params.append(f"edges={edges_param}")

            cuboid_params.append(f"anchor={anchor}")
            cuboid_call = f"cuboid({', '.join(cuboid_params)});"

            transform_lines, indent = generate_transform_prefix(feature_info, (cx, cy))
            lines.extend(transform_lines)
            lines.append(f"{indent}{cuboid_call}")

        else:
            cx, cy = profile.get('center', (0, 0))
            transform_lines, indent = generate_transform_prefix(feature_info, (0, 0))
            lines.extend(transform_lines)

            if PROFILE_UTILS_AVAILABLE and 'profile_obj' in profile:
                try:
                    poly_data = extract_profile_polygon(profile['profile_obj'])
                    has_holes = bool(poly_data['holes'])

                    if rounding and rounding > 0:
                        # Calculate effective rounding
                        height_val = abs(raw_height)
                        max_rounding_height = height_val / 2 * 0.95
                        max_rounding_path = calculate_max_inset(poly_data['outer'])
                        max_rounding = min(max_rounding_height, max_rounding_path)
                        effective_rounding = min(rounding, max_rounding)

                        # If effective rounding is 0 or very small, fall back to linear_extrude
                        if effective_rounding < 0.1:
                            if warnings:
                                warnings.add_warning(
                                    feature_name,
                                    f"rounding skipped (profile geometry unsuitable for offset_sweep)",
                                    "constraint"
                                )
                            # Generate simple extrusion instead
                            if has_holes:
                                polygon_code = format_polygon_with_holes_scad(
                                    poly_data['outer'], poly_data['holes']
                                )
                            else:
                                polygon_code = format_polygon_scad(poly_data['outer'])

                            lines.append(f"{indent}// Note: rounding skipped due to profile constraints")
                            lines.append(f"{indent}linear_extrude(height={abs_height})")
                            poly_lines = polygon_code.split('\n')
                            for i, poly_line in enumerate(poly_lines):
                                if i == len(poly_lines) - 1:
                                    lines.append(f"{indent}    {poly_line};")
                                else:
                                    lines.append(f"{indent}    {poly_line}")
                        else:
                            if effective_rounding < rounding:
                                reason = "height" if max_rounding_height < max_rounding_path else "profile size"
                                if warnings:
                                    warnings.add_warning(
                                        feature_name,
                                        f"rounding reduced {format_value(rounding)}->{format_value(effective_rounding)}mm ({reason} constraint)",
                                        "constraint"
                                    )

                            # If profile has holes, wrap in difference()
                            if has_holes:
                                lines.append(f"{indent}difference() {{")
                                inner_indent = indent + "    "
                            else:
                                inner_indent = indent

                            lines.append(f"{inner_indent}// Using BOSL2 offset_sweep for rounded extrusion")
                            lines.append(f"{inner_indent}offset_sweep(")
                            formatted_pts = []
                            for x, y in poly_data['outer']:
                                fx = f"{x:.4f}".rstrip('0').rstrip('.')
                                fy = f"{y:.4f}".rstrip('0').rstrip('.')
                                formatted_pts.append(f"[{fx}, {fy}]")
                            points_str = ", ".join(formatted_pts)
                            lines.append(f"{inner_indent}    [{points_str}],")
                            lines.append(f"{inner_indent}    height={abs_height},")
                            if effective_rounding < rounding:
                                lines.append(f"{inner_indent}    // Note: rounding reduced from {format_value(rounding)} to {format_value(effective_rounding)} to fit {reason}")
                            lines.append(f"{inner_indent}    top=os_circle(r={format_value(effective_rounding)}),")
                            lines.append(f"{inner_indent}    bottom=os_circle(r={format_value(effective_rounding)})")
                            lines.append(f"{inner_indent});")

                            # Cut out holes if present
                            if has_holes:
                                lines.append(f"{inner_indent}// Cut out holes")
                                for hole in poly_data['holes']:
                                    hole_lines = generate_hole_cut(hole, abs_height, inner_indent)
                                    lines.extend(hole_lines)
                                lines.append(f"{indent}}}") 
                    elif chamfer and chamfer > 0:
                        # Calculate effective chamfer
                        height_val = abs(raw_height)
                        max_chamfer_height = height_val / 2 * 0.95
                        max_chamfer_path = calculate_max_inset(poly_data['outer'])
                        max_chamfer_val = min(max_chamfer_height, max_chamfer_path)
                        effective_chamfer = min(chamfer, max_chamfer_val)

                        # If effective chamfer is 0 or very small, fall back to linear_extrude
                        if effective_chamfer < 0.1:
                            if warnings:
                                warnings.add_warning(
                                    feature_name,
                                    f"chamfer skipped (profile geometry unsuitable for offset_sweep)",
                                    "constraint"
                                )
                            # Generate simple extrusion instead
                            if has_holes:
                                polygon_code = format_polygon_with_holes_scad(
                                    poly_data['outer'], poly_data['holes']
                                )
                            else:
                                polygon_code = format_polygon_scad(poly_data['outer'])

                            lines.append(f"{indent}// Note: chamfer skipped due to profile constraints")
                            lines.append(f"{indent}linear_extrude(height={abs_height})")
                            poly_lines = polygon_code.split('\n')
                            for i, poly_line in enumerate(poly_lines):
                                if i == len(poly_lines) - 1:
                                    lines.append(f"{indent}    {poly_line};")
                                else:
                                    lines.append(f"{indent}    {poly_line}")
                        else:
                            if effective_chamfer < chamfer:
                                reason = "height" if max_chamfer_height < max_chamfer_path else "profile size"
                                if warnings:
                                    warnings.add_warning(
                                        feature_name,
                                        f"chamfer reduced {format_value(chamfer)}->{format_value(effective_chamfer)}mm ({reason} constraint)",
                                        "constraint"
                                    )

                            # If profile has holes, wrap in difference()
                            if has_holes:
                                lines.append(f"{indent}difference() {{")
                                inner_indent = indent + "    "
                            else:
                                inner_indent = indent

                            lines.append(f"{inner_indent}// Using BOSL2 offset_sweep for chamfered extrusion")
                            lines.append(f"{inner_indent}offset_sweep(")
                            formatted_pts = []
                            for x, y in poly_data['outer']:
                                fx = f"{x:.4f}".rstrip('0').rstrip('.')
                                fy = f"{y:.4f}".rstrip('0').rstrip('.')
                                formatted_pts.append(f"[{fx}, {fy}]")
                            points_str = ", ".join(formatted_pts)
                            lines.append(f"{inner_indent}    [{points_str}],")
                            lines.append(f"{inner_indent}    height={abs_height},")
                            if effective_chamfer < chamfer:
                                lines.append(f"{inner_indent}    // Note: chamfer reduced from {format_value(chamfer)} to {format_value(effective_chamfer)} to fit {reason}")
                            lines.append(f"{inner_indent}    top=os_chamfer(height={format_value(effective_chamfer)}),")
                            lines.append(f"{inner_indent}    bottom=os_chamfer(height={format_value(effective_chamfer)})")
                            lines.append(f"{inner_indent});")

                            # Cut out holes if present
                            if has_holes:
                                lines.append(f"{inner_indent}// Cut out holes")
                                for hole in poly_data['holes']:
                                    hole_lines = generate_hole_cut(hole, abs_height, inner_indent)
                                    lines.extend(hole_lines)
                                lines.append(f"{indent}}}") 
                    else:
                        # Simple extrusion without rounding/chamfer
                        if has_holes:
                            # Use polygon with paths for holes
                            polygon_code = format_polygon_with_holes_scad(
                                poly_data['outer'], poly_data['holes']
                            )
                        else:
                            polygon_code = format_polygon_scad(poly_data['outer'])
                        
                        lines.append(f"{indent}linear_extrude(height={height})")
                        poly_lines = polygon_code.split('\n')
                        for i, poly_line in enumerate(poly_lines):
                            if i == len(poly_lines) - 1:
                                lines.append(f"{indent}    {poly_line};")
                            else:
                                lines.append(f"{indent}    {poly_line}")
                except:
                    lines.append(f"{indent}// Complex profile - manual adjustment needed")
                    lines.append(f"{indent}linear_extrude(height={height})")
                    lines.append(f"{indent}    polygon(points=[/* extracted points would go here */]);")
            else:
                lines.append(f"{indent}// Complex profile - install profile_utils for auto-extraction")
                lines.append(f"{indent}linear_extrude(height={height})")
                lines.append(f"{indent}    polygon(points=[/* extracted points would go here */]);")

    return lines


def generate_revolve_scad(feature_info: dict, feature_name: str) -> list:
    """Generate BOSL2 code for a revolution"""
    lines = []
    angle = format_value(feature_info['angle'])

    lines.append(f"// {feature_name}")
    if feature_info['angle'] == 360:
        lines.append("rotate_extrude()")
    else:
        lines.append(f"rotate_extrude(angle={angle})")
    lines.append("    polygon(points=[/* profile points */]);")

    return lines


def generate_hole_scad(feature_info: dict, feature_name: str) -> list:
    """Generate BOSL2 code for holes including countersink and counterbore"""
    lines = []

    diameter = feature_info['diameter']
    radius = format_value(diameter / 2)
    depth = feature_info['depth']
    matrix = feature_info.get('matrix')
    hole_type = feature_info.get('hole_type', 'simple')

    lines.append(f"// {feature_name} ({hole_type})")

    for x, y, z in feature_info['positions']:
        epsilon = 1.0
        total_h = format_value(depth + epsilon)

        lines.append(f"translate([{format_value(x)}, {format_value(y)}, {format_value(z)}])")

        if matrix:
            matrix_str = "[\n"
            for row in matrix:
                row_str = ", ".join(format_value(v) for v in row)
                matrix_str += f"        [{row_str}],\n"
            matrix_str = matrix_str.rstrip(",\n") + "\n    ]"
            lines.append(f"    multmatrix({matrix_str})")

        indent = "    "

        if hole_type == 'countersink':
            cs_diameter = feature_info.get('countersink_diameter', diameter * 2)
            cs_angle = feature_info.get('countersink_angle', 90)
            cs_radius = cs_diameter / 2
            # Calculate countersink depth from angle and radius difference
            # For a 90° countersink: depth = radius_diff
            # For other angles: depth = radius_diff / tan(angle/2)
            radius_diff = cs_radius - (diameter / 2)
            half_angle_rad = math.radians(cs_angle / 2)
            cs_depth = radius_diff / math.tan(half_angle_rad) if half_angle_rad > 0 else radius_diff

            lines.append(f"{indent}union() {{")
            lines.append(f"{indent}    // Main hole")
            lines.append(f"{indent}    translate([0, 0, -{epsilon}])")
            lines.append(f"{indent}        cyl(h={total_h}, r={radius}, anchor=BOTTOM);")
            lines.append(f"{indent}    // Countersink cone")
            lines.append(f"{indent}    translate([0, 0, -{format_value(cs_depth)}])")
            lines.append(f"{indent}        cyl(h={format_value(cs_depth + epsilon)}, r1={format_value(cs_radius)}, r2={radius}, anchor=BOTTOM);")
            lines.append(f"{indent}}}")

        elif hole_type == 'counterbore':
            cb_diameter = feature_info.get('counterbore_diameter', diameter * 1.5)
            cb_depth = feature_info.get('counterbore_depth', 2)
            cb_radius = format_value(cb_diameter / 2)

            lines.append(f"{indent}union() {{")
            lines.append(f"{indent}    // Main hole")
            lines.append(f"{indent}    translate([0, 0, -{epsilon}])")
            lines.append(f"{indent}        cyl(h={total_h}, r={radius}, anchor=BOTTOM);")
            lines.append(f"{indent}    // Counterbore")
            lines.append(f"{indent}    translate([0, 0, -{format_value(cb_depth)}])")
            lines.append(f"{indent}        cyl(h={format_value(cb_depth + epsilon)}, r={cb_radius}, anchor=BOTTOM);")
            lines.append(f"{indent}}}")

        else:
            # Simple hole
            lines.append(f"{indent}translate([0, 0, -{epsilon}])")
            lines.append(f"{indent}cyl(h={total_h}, r={radius}, anchor=BOTTOM);")

    return lines
