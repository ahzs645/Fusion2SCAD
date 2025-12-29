#Author: Fusion2SCAD
#Description: Feature analysis functions for Fusion 360 to OpenSCAD export

import math
import adsk.core
import adsk.fusion

from .utils import CM_TO_MM, get_rotation_matrix_from_axis


def extract_sketch_geometry(sketch: adsk.fusion.Sketch) -> dict:
    """Extract geometry from a Fusion 360 sketch"""
    geometry = {
        'lines': [],
        'circles': [],
        'arcs': [],
        'rectangles': [],
        'points': [],
        'profiles': []
    }

    # Extract sketch curves
    for curve in sketch.sketchCurves:
        if isinstance(curve, adsk.fusion.SketchLine):
            start = curve.startSketchPoint.geometry
            end = curve.endSketchPoint.geometry
            geometry['lines'].append({
                'start': (start.x * CM_TO_MM, start.y * CM_TO_MM),
                'end': (end.x * CM_TO_MM, end.y * CM_TO_MM)
            })
        elif isinstance(curve, adsk.fusion.SketchCircle):
            center = curve.centerSketchPoint.geometry
            geometry['circles'].append({
                'center': (center.x * CM_TO_MM, center.y * CM_TO_MM),
                'radius': curve.radius * CM_TO_MM
            })
        elif isinstance(curve, adsk.fusion.SketchArc):
            center = curve.centerSketchPoint.geometry
            geometry['arcs'].append({
                'center': (center.x * CM_TO_MM, center.y * CM_TO_MM),
                'radius': curve.radius * CM_TO_MM,
                'start_angle': math.degrees(curve.startAngle),
                'end_angle': math.degrees(curve.endAngle)
            })

    # Try to detect rectangles from sketch profiles
    for profile in sketch.profiles:
        loops = profile.profileLoops
        for loop in loops:
            curves = loop.profileCurves
            if len(curves) == 4:
                all_lines = all(isinstance(c.sketchEntity, adsk.fusion.SketchLine) for c in curves)
                if all_lines:
                    bbox = profile.boundingBox
                    min_pt = bbox.minPoint
                    max_pt = bbox.maxPoint
                    width = (max_pt.x - min_pt.x) * CM_TO_MM
                    height = (max_pt.y - min_pt.y) * CM_TO_MM
                    center_x = (min_pt.x + max_pt.x) / 2 * CM_TO_MM
                    center_y = (min_pt.y + max_pt.y) / 2 * CM_TO_MM
                    geometry['rectangles'].append({
                        'width': width,
                        'height': height,
                        'center': (center_x, center_y)
                    })

    return geometry


def analyze_profile(profile: adsk.fusion.Profile) -> dict:
    """Analyze a sketch profile to determine its shape"""
    info = {
        'shape': 'polygon',
        'bbox': None,
        'center': None,
        'is_circle': False,
        'is_rectangle': False,
        'is_rounded_rect': False,
        'profile_obj': profile
    }

    bbox = profile.boundingBox
    min_pt = bbox.minPoint
    max_pt = bbox.maxPoint

    width = (max_pt.x - min_pt.x) * CM_TO_MM
    height = (max_pt.y - min_pt.y) * CM_TO_MM
    center_x = (min_pt.x + max_pt.x) / 2 * CM_TO_MM
    center_y = (min_pt.y + max_pt.y) / 2 * CM_TO_MM

    info['bbox'] = {'width': width, 'height': height}
    info['center'] = (center_x, center_y)

    # Check if it's a circle
    loops = profile.profileLoops
    if loops.count == 1:
        curves = loops.item(0).profileCurves
        if curves.count == 1:
            entity = curves.item(0).sketchEntity
            if isinstance(entity, adsk.fusion.SketchCircle):
                info['is_circle'] = True
                info['shape'] = 'circle'
                info['radius'] = entity.radius * CM_TO_MM
        elif curves.count == 4:
            all_lines = all(
                isinstance(curves.item(i).sketchEntity, adsk.fusion.SketchLine)
                for i in range(4)
            )
            if all_lines:
                info['is_rectangle'] = True
                info['shape'] = 'rectangle'

        elif curves.count == 8:
            lines = []
            arcs = []
            for i in range(curves.count):
                entity = curves.item(i).sketchEntity
                if isinstance(entity, adsk.fusion.SketchLine):
                    lines.append(entity)
                elif isinstance(entity, adsk.fusion.SketchArc):
                    arcs.append(entity)

            if len(lines) == 4 and len(arcs) == 4:
                radii = [arc.radius * CM_TO_MM for arc in arcs]
                if max(radii) - min(radii) < 0.01:
                    info['is_rounded_rect'] = True
                    info['shape'] = 'rounded_rect'
                    info['rounding'] = radii[0]

    return info


def get_operation_type(operation) -> str:
    """Convert Fusion operation type to OpenSCAD equivalent"""
    op_map = {
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation: 'new',
        adsk.fusion.FeatureOperations.JoinFeatureOperation: 'union',
        adsk.fusion.FeatureOperations.CutFeatureOperation: 'difference',
        adsk.fusion.FeatureOperations.IntersectFeatureOperation: 'intersection'
    }
    return op_map.get(operation, 'union')


def analyze_extrude_feature(feature: adsk.fusion.ExtrudeFeature) -> dict:
    """Analyze an extrude feature and determine best BOSL2 representation"""
    result = {
        'type': 'extrude',
        'operation': get_operation_type(feature.operation),
        'height': None,
        'profiles': [],
        'is_symmetric': False,
        'taper_angle': 0,
        'sketch_plane': 'XY',
        'plane_origin': (0, 0, 0),
        'plane_normal': (0, 0, 1),
        'rotation': None
    }

    # Get extrusion extent
    extent_def = feature.extentOne
    if isinstance(extent_def, adsk.fusion.DistanceExtentDefinition):
        result['height'] = extent_def.distance.value * CM_TO_MM

    # Check for symmetric extrusion
    if feature.extentTwo:
        result['is_symmetric'] = True

    # Get taper angle if present
    if feature.taperAngleOne:
        result['taper_angle'] = math.degrees(feature.taperAngleOne.value)

    # Get the sketch plane orientation and origin
    try:
        profiles = feature.profile
        profile = profiles if isinstance(profiles, adsk.fusion.Profile) else profiles.item(0)
        sketch = profile.parentSketch

        if sketch:
            origin = sketch.origin
            result['plane_origin'] = (
                origin.x * CM_TO_MM,
                origin.y * CM_TO_MM,
                origin.z * CM_TO_MM
            )

            transform = sketch.transform
            if transform:
                cs = transform.getAsCoordinateSystem()
                origin_pt, x_axis, y_axis, z_axis = cs

                result['sketch_transform'] = {
                    'origin': (origin_pt.x, origin_pt.y, origin_pt.z),
                    'x_axis': (x_axis.x, x_axis.y, x_axis.z),
                    'y_axis': (y_axis.x, y_axis.y, y_axis.z),
                    'z_axis': (z_axis.x, z_axis.y, z_axis.z)
                }

                result['plane_normal'] = (z_axis.x, z_axis.y, z_axis.z)

                nx, ny, nz = z_axis.x, z_axis.y, z_axis.z
                tolerance = 0.001

                if abs(nz - 1) < tolerance or abs(nz + 1) < tolerance:
                    result['sketch_plane'] = 'XY'
                elif abs(ny - 1) < tolerance or abs(ny + 1) < tolerance:
                    result['sketch_plane'] = 'XZ'
                elif abs(nx - 1) < tolerance or abs(nx + 1) < tolerance:
                    result['sketch_plane'] = 'YZ'
                else:
                    result['sketch_plane'] = 'CUSTOM'
    except:
        pass

    # Analyze the profile to determine shape type
    profiles = feature.profile
    if isinstance(profiles, adsk.fusion.Profile):
        profile_info = analyze_profile(profiles)
        result['profiles'].append(profile_info)
    else:
        try:
            for i in range(profiles.count):
                profile = profiles.item(i)
                if isinstance(profile, adsk.fusion.Profile):
                    profile_info = analyze_profile(profile)
                    result['profiles'].append(profile_info)
        except:
            try:
                for profile in profiles:
                    if isinstance(profile, adsk.fusion.Profile):
                        profile_info = analyze_profile(profile)
                        result['profiles'].append(profile_info)
            except:
                pass

    return result


def analyze_revolve_feature(feature: adsk.fusion.RevolveFeature) -> dict:
    """Analyze a revolve feature"""
    result = {
        'type': 'revolve',
        'operation': get_operation_type(feature.operation),
        'angle': 360,
        'profiles': []
    }

    extent_def = feature.extentDefinition
    if isinstance(extent_def, adsk.fusion.AngleExtentDefinition):
        result['angle'] = math.degrees(extent_def.angle.value)

    profiles = feature.profile
    if isinstance(profiles, adsk.fusion.Profile):
        profile_info = analyze_profile(profiles)
        result['profiles'].append(profile_info)
    else:
        try:
            for i in range(profiles.count):
                profile = profiles.item(i)
                if isinstance(profile, adsk.fusion.Profile):
                    profile_info = analyze_profile(profile)
                    result['profiles'].append(profile_info)
        except:
            pass

    return result


def analyze_hole_feature(feature: adsk.fusion.HoleFeature) -> dict:
    """Analyze a hole feature by inspecting its geometry"""
    result = {
        'type': 'hole',
        'diameter': 0,
        'depth': 50,
        'positions': [],
        'matrix': None
    }

    try:
        if feature.holeDiameter:
            result['diameter'] = feature.holeDiameter.value * CM_TO_MM

        extent = feature.extentDefinition
        if isinstance(extent, adsk.fusion.DistanceExtentDefinition):
            result['depth'] = extent.distance.value * CM_TO_MM
        elif isinstance(extent, adsk.fusion.ThroughAllExtentDefinition):
            result['depth'] = 200

        start_pos = None
        if feature.position:
            p = feature.position
            start_pos = (p.x * CM_TO_MM, p.y * CM_TO_MM, p.z * CM_TO_MM)

        faces = feature.faces
        for i in range(faces.count):
            face = faces.item(i)
            geom = face.geometry
            if isinstance(geom, adsk.core.Cylinder):
                origin = geom.origin
                axis = geom.axis

                if not start_pos:
                    start_pos = (
                        origin.x * CM_TO_MM,
                        origin.y * CM_TO_MM,
                        origin.z * CM_TO_MM
                    )

                if result['matrix'] is None:
                    result['matrix'] = get_rotation_matrix_from_axis(axis)

                break

        if start_pos:
            result['positions'].append(start_pos)

    except:
        pass

    return result


def analyze_fillet_feature(feature: adsk.fusion.FilletFeature) -> dict:
    """Analyze a fillet feature and track which bodies it affects"""
    result = {
        'type': 'fillet',
        'radius': 0,
        'edges': [],
        'affected_bodies': set()
    }

    edge_sets = feature.edgeSets
    if edge_sets.count > 0:
        edge_set = edge_sets.item(0)
        if isinstance(edge_set, adsk.fusion.ConstantRadiusFilletEdgeSet):
            result['radius'] = edge_set.radius.value * CM_TO_MM
            try:
                edges = edge_set.edges
                for edge in edges:
                    body = edge.body
                    if body:
                        result['affected_bodies'].add(body.entityToken)
            except:
                pass

    return result


def analyze_chamfer_feature(feature: adsk.fusion.ChamferFeature) -> dict:
    """Analyze a chamfer feature and track which bodies it affects"""
    result = {
        'type': 'chamfer',
        'distance': 0,
        'affected_bodies': set()
    }

    edge_sets = feature.edgeSets
    if edge_sets.count > 0:
        edge_set = edge_sets.item(0)
        if isinstance(edge_set, adsk.fusion.EqualDistanceChamferEdgeSet):
            result['distance'] = edge_set.distance.value * CM_TO_MM
            try:
                edges = edge_set.edges
                for edge in edges:
                    body = edge.body
                    if body:
                        result['affected_bodies'].add(body.entityToken)
            except:
                pass

    return result
