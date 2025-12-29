#Author: Fusion2SCAD
#Description: Utilities for extracting and converting Fusion 360 sketch profiles to OpenSCAD polygons

import adsk.core, adsk.fusion
import math

CM_TO_MM = 10.0


def approximate_arc_points(center_x: float, center_y: float, radius: float,
                           start_angle: float, end_angle: float,
                           segments: int = 16) -> list:
    """
    Approximate an arc with a series of points for polygon representation.

    Args:
        center_x, center_y: Arc center in mm
        radius: Arc radius in mm
        start_angle, end_angle: Angles in radians
        segments: Number of segments to approximate the arc

    Returns:
        List of (x, y) tuples
    """
    points = []
    angle_span = end_angle - start_angle

    # Handle negative spans (arc going clockwise)
    if angle_span < 0:
        angle_span += 2 * math.pi

    for i in range(segments + 1):
        t = i / segments
        angle = start_angle + t * angle_span
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))

    return points


def approximate_ellipse_points(center_x: float, center_y: float,
                               major_radius: float, minor_radius: float,
                               rotation: float = 0,
                               segments: int = 32) -> list:
    """
    Approximate an ellipse with a series of points.

    Args:
        center_x, center_y: Ellipse center in mm
        major_radius, minor_radius: Radii in mm
        rotation: Rotation angle in radians
        segments: Number of segments

    Returns:
        List of (x, y) tuples
    """
    points = []
    cos_rot = math.cos(rotation)
    sin_rot = math.sin(rotation)

    for i in range(segments):
        t = 2 * math.pi * i / segments
        # Point on unrotated ellipse
        px = major_radius * math.cos(t)
        py = minor_radius * math.sin(t)
        # Apply rotation
        x = center_x + px * cos_rot - py * sin_rot
        y = center_y + px * sin_rot + py * cos_rot
        points.append((x, y))

    return points


def approximate_spline_points(spline, segments: int = 32) -> list:
    """
    Approximate a spline curve with a series of points.

    Args:
        spline: Fusion 360 SketchFittedSpline or SketchFixedSpline
        segments: Number of segments

    Returns:
        List of (x, y) tuples
    """
    points = []
    evaluator = spline.geometry.evaluator

    # Get the parameter range
    (return_val, start_param, end_param) = evaluator.getParameterExtents()
    if not return_val:
        return points

    param_span = end_param - start_param

    for i in range(segments + 1):
        t = start_param + (i / segments) * param_span
        (return_val, point) = evaluator.getPointAtParameter(t)
        if return_val:
            points.append((point.x * CM_TO_MM, point.y * CM_TO_MM))

    return points


def extract_profile_polygon(profile: adsk.fusion.Profile, arc_segments: int = 16) -> dict:
    """
    Extract a complete polygon representation from a Fusion 360 profile.

    Args:
        profile: Fusion 360 Profile object
        arc_segments: Number of segments for arc approximation

    Returns:
        Dictionary with 'outer' points and 'holes' list of point lists
    """
    result = {
        'outer': [],
        'holes': []
    }

    for loop_idx in range(profile.profileLoops.count):
        loop = profile.profileLoops.item(loop_idx)
        points = []

        for curve_idx in range(loop.profileCurves.count):
            curve = loop.profileCurves.item(curve_idx)
            entity = curve.sketchEntity

            if isinstance(entity, adsk.fusion.SketchLine):
                # Add line start point (end point will be added by next segment)
                start = entity.startSketchPoint.geometry
                points.append((start.x * CM_TO_MM, start.y * CM_TO_MM))

            elif isinstance(entity, adsk.fusion.SketchArc):
                center = entity.centerSketchPoint.geometry
                arc_points = approximate_arc_points(
                    center.x * CM_TO_MM,
                    center.y * CM_TO_MM,
                    entity.radius * CM_TO_MM,
                    entity.startAngle,
                    entity.endAngle,
                    arc_segments
                )
                # Don't add the last point as it will be the start of next curve
                points.extend(arc_points[:-1])

            elif isinstance(entity, adsk.fusion.SketchCircle):
                center = entity.centerSketchPoint.geometry
                circle_points = approximate_arc_points(
                    center.x * CM_TO_MM,
                    center.y * CM_TO_MM,
                    entity.radius * CM_TO_MM,
                    0,
                    2 * math.pi,
                    arc_segments * 2
                )
                points.extend(circle_points[:-1])

            elif isinstance(entity, adsk.fusion.SketchEllipse):
                center = entity.centerSketchPoint.geometry
                ellipse_points = approximate_ellipse_points(
                    center.x * CM_TO_MM,
                    center.y * CM_TO_MM,
                    entity.majorRadius * CM_TO_MM,
                    entity.minorRadius * CM_TO_MM,
                    0,  # TODO: Extract rotation
                    arc_segments * 2
                )
                points.extend(ellipse_points)

            elif isinstance(entity, (adsk.fusion.SketchFittedSpline, adsk.fusion.SketchFixedSpline)):
                spline_points = approximate_spline_points(entity, arc_segments * 2)
                points.extend(spline_points[:-1])

        # Remove duplicate consecutive points
        cleaned_points = remove_duplicate_points(points)

        # First loop is outer boundary, rest are holes
        if loop.isOuter:
            result['outer'] = cleaned_points
        else:
            result['holes'].append(cleaned_points)

    return result


def remove_duplicate_points(points: list, tolerance: float = 0.001) -> list:
    """Remove consecutive duplicate points within tolerance"""
    if not points:
        return points

    cleaned = [points[0]]
    for pt in points[1:]:
        last = cleaned[-1]
        dist = math.sqrt((pt[0] - last[0])**2 + (pt[1] - last[1])**2)
        if dist > tolerance:
            cleaned.append(pt)

    return cleaned


def format_polygon_scad(points: list, precision: int = 4) -> str:
    """
    Format a list of points as an OpenSCAD polygon.

    Args:
        points: List of (x, y) tuples
        precision: Decimal precision for coordinates

    Returns:
        OpenSCAD polygon() call as string
    """
    formatted_points = []
    for x, y in points:
        fx = f"{x:.{precision}f}".rstrip('0').rstrip('.')
        fy = f"{y:.{precision}f}".rstrip('0').rstrip('.')
        formatted_points.append(f"[{fx}, {fy}]")

    points_str = ",\n        ".join(formatted_points)
    return f"polygon(points=[\n        {points_str}\n    ])"


def format_polygon_with_holes_scad(outer: list, holes: list, precision: int = 4) -> str:
    """
    Format a polygon with holes for OpenSCAD.

    Args:
        outer: List of (x, y) tuples for outer boundary
        holes: List of lists of (x, y) tuples for holes
        precision: Decimal precision

    Returns:
        OpenSCAD polygon() call with paths as string
    """
    all_points = list(outer)
    paths = [list(range(len(outer)))]

    for hole in holes:
        start_idx = len(all_points)
        all_points.extend(hole)
        paths.append(list(range(start_idx, start_idx + len(hole))))

    # Format points
    formatted_points = []
    for x, y in all_points:
        fx = f"{x:.{precision}f}".rstrip('0').rstrip('.')
        fy = f"{y:.{precision}f}".rstrip('0').rstrip('.')
        formatted_points.append(f"[{fx}, {fy}]")

    points_str = ",\n        ".join(formatted_points)
    paths_str = ", ".join(str(p) for p in paths)

    return f"polygon(\n    points=[\n        {points_str}\n    ],\n    paths=[{paths_str}]\n)"


def detect_shape_type(profile: adsk.fusion.Profile) -> dict:
    """
    Analyze a profile to detect if it's a standard shape.

    Returns dict with:
        - 'type': 'circle', 'rectangle', 'rounded_rect', 'polygon'
        - Shape-specific parameters
    """
    result = {'type': 'polygon'}

    loops = profile.profileLoops
    if loops.count != 1:
        return result  # Has holes, treat as polygon

    loop = loops.item(0)
    curves = loop.profileCurves

    # Single circle
    if curves.count == 1:
        entity = curves.item(0).sketchEntity
        if isinstance(entity, adsk.fusion.SketchCircle):
            center = entity.centerSketchPoint.geometry
            return {
                'type': 'circle',
                'center': (center.x * CM_TO_MM, center.y * CM_TO_MM),
                'radius': entity.radius * CM_TO_MM
            }

    # Rectangle (4 lines)
    if curves.count == 4:
        all_lines = all(
            isinstance(curves.item(i).sketchEntity, adsk.fusion.SketchLine)
            for i in range(4)
        )
        if all_lines:
            bbox = profile.boundingBox
            min_pt = bbox.minPoint
            max_pt = bbox.maxPoint
            width = (max_pt.x - min_pt.x) * CM_TO_MM
            height = (max_pt.y - min_pt.y) * CM_TO_MM
            center_x = (min_pt.x + max_pt.x) / 2 * CM_TO_MM
            center_y = (min_pt.y + max_pt.y) / 2 * CM_TO_MM

            return {
                'type': 'rectangle',
                'center': (center_x, center_y),
                'width': width,
                'height': height
            }

    # Rounded rectangle (4 lines + 4 arcs)
    if curves.count == 8:
        lines = []
        arcs = []
        for i in range(curves.count):
            entity = curves.item(i).sketchEntity
            if isinstance(entity, adsk.fusion.SketchLine):
                lines.append(entity)
            elif isinstance(entity, adsk.fusion.SketchArc):
                arcs.append(entity)

        if len(lines) == 4 and len(arcs) == 4:
            # Check if all arcs have same radius
            radii = [arc.radius * CM_TO_MM for arc in arcs]
            if max(radii) - min(radii) < 0.01:  # Within tolerance
                bbox = profile.boundingBox
                min_pt = bbox.minPoint
                max_pt = bbox.maxPoint
                width = (max_pt.x - min_pt.x) * CM_TO_MM
                height = (max_pt.y - min_pt.y) * CM_TO_MM
                center_x = (min_pt.x + max_pt.x) / 2 * CM_TO_MM
                center_y = (min_pt.y + max_pt.y) / 2 * CM_TO_MM

                return {
                    'type': 'rounded_rect',
                    'center': (center_x, center_y),
                    'width': width,
                    'height': height,
                    'rounding': radii[0]
                }

    return result


def generate_bosl2_shape(shape_info: dict, height: float = None) -> str:
    """
    Generate BOSL2 code for a detected shape.

    Args:
        shape_info: Dictionary from detect_shape_type()
        height: Extrusion height (None for 2D)

    Returns:
        BOSL2 code string
    """

    def fmt(v):
        return f"{v:.4f}".rstrip('0').rstrip('.')

    shape_type = shape_info['type']
    cx, cy = shape_info.get('center', (0, 0))
    translate_needed = abs(cx) > 0.001 or abs(cy) > 0.001

    if shape_type == 'circle':
        radius = shape_info['radius']
        if height:
            shape = f"cyl(h={fmt(height)}, r={fmt(radius)}, anchor=BOTTOM)"
        else:
            shape = f"circle(r={fmt(radius)})"

    elif shape_type == 'rectangle':
        w, h = shape_info['width'], shape_info['height']
        if height:
            shape = f"cuboid([{fmt(w)}, {fmt(h)}, {fmt(height)}], anchor=BOTTOM)"
        else:
            shape = f"rect([{fmt(w)}, {fmt(h)}])"

    elif shape_type == 'rounded_rect':
        w, h = shape_info['width'], shape_info['height']
        r = shape_info['rounding']
        if height:
            shape = f"cuboid([{fmt(w)}, {fmt(h)}, {fmt(height)}], rounding={fmt(r)}, anchor=BOTTOM)"
        else:
            shape = f"rect([{fmt(w)}, {fmt(h)}], rounding={fmt(r)})"

    else:
        # Generic polygon - caller should use format_polygon_scad
        return None

    if translate_needed:
        return f"translate([{fmt(cx)}, {fmt(cy)}, 0])\n    {shape}"
    return shape
