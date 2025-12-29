#Author: Fusion2SCAD
#Description: Main SCADExporter class for Fusion 360 to OpenSCAD export

import adsk.core
import adsk.fusion

from .utils import CM_TO_MM, sanitize_name, format_value
from .analyzers import (
    analyze_extrude_feature,
    analyze_revolve_feature,
    analyze_hole_feature,
    analyze_fillet_feature,
    analyze_chamfer_feature
)
from .generators import (
    generate_header,
    generate_parameters_section,
    generate_extrude_scad,
    generate_revolve_scad,
    generate_hole_scad
)


class SCADExporter:
    """Main exporter class that converts Fusion 360 design to OpenSCAD/BOSL2 code"""

    def __init__(self, design: adsk.fusion.Design):
        self.design = design
        self.parameters = {}
        self.scad_lines = []
        self.indent_level = 0
        self.processed_bodies = set()
        self.feature_map = {}
        self.body_to_feature = {}
        self.feature_modifiers = {}

    def indent(self):
        return "    " * self.indent_level

    def add_line(self, line: str):
        self.scad_lines.append(f"{self.indent()}{line}")

    def add_blank(self):
        self.scad_lines.append("")

    def extract_parameters(self):
        """Extract all user-defined parameters from the design"""
        params = self.design.userParameters
        for i in range(params.count):
            param = params.item(i)
            name = sanitize_name(param.name)
            value = param.value * CM_TO_MM
            unit = param.unit
            comment = param.comment if param.comment else ""
            self.parameters[param.name] = {
                'name': name,
                'value': value,
                'unit': unit,
                'comment': comment,
                'expression': param.expression
            }
        return self.parameters

    def _get_param_or_value(self, fusion_value: float, fusion_expression: str = None) -> str:
        """Return parameter name if it matches, otherwise return the numeric value"""
        value_mm = fusion_value * CM_TO_MM

        if fusion_expression:
            for orig_name, param_info in self.parameters.items():
                if orig_name in fusion_expression:
                    return param_info['name']

        return format_value(value_mm)

    def process_timeline(self) -> list:
        """Process the design timeline and generate SCAD code for each feature.
        Uses a two-pass approach to associate fillets/chamfers with their parent shapes."""
        scad_code = []
        timeline = self.design.timeline

        # PASS 1: Collect all features and associate modifiers
        features_data = []
        feature_to_bodies = {}
        body_modifiers = {}

        for i in range(timeline.count):
            item = timeline.item(i)
            entity = item.entity

            if entity is None:
                continue

            feature_name = item.name if hasattr(item, 'name') else f"feature_{i}"

            try:
                if isinstance(entity, adsk.fusion.ExtrudeFeature):
                    info = analyze_extrude_feature(entity)
                    features_data.append((entity, feature_name, info, 'extrude'))

                    try:
                        for body in entity.bodies:
                            token = body.entityToken
                            feature_to_bodies[len(features_data) - 1] = token
                            if token not in body_modifiers:
                                body_modifiers[token] = {'rounding': 0, 'chamfer': 0}
                    except:
                        pass

                elif isinstance(entity, adsk.fusion.RevolveFeature):
                    info = analyze_revolve_feature(entity)
                    features_data.append((entity, feature_name, info, 'revolve'))

                    try:
                        for body in entity.bodies:
                            token = body.entityToken
                            feature_to_bodies[len(features_data) - 1] = token
                            if token not in body_modifiers:
                                body_modifiers[token] = {'rounding': 0, 'chamfer': 0}
                    except:
                        pass

                elif isinstance(entity, adsk.fusion.HoleFeature):
                    info = analyze_hole_feature(entity)
                    features_data.append((entity, feature_name, info, 'hole'))

                # Disable 3D Fillet/Chamfer application for now as it applies globally to shapes
                # causing incorrect geometry (e.g. rounding all edges of a cube).
                # 2D Sketch fillets are still handled by analyze_profile.
                # elif isinstance(entity, adsk.fusion.FilletFeature):
                #     info = analyze_fillet_feature(entity)
                #     for body_token in info['affected_bodies']:
                #         if body_token in body_modifiers:
                #             body_modifiers[body_token]['rounding'] = max(
                #                 body_modifiers[body_token]['rounding'],
                #                 info['radius']
                #             )
                #         else:
                #             body_modifiers[body_token] = {'rounding': info['radius'], 'chamfer': 0}
                #
                # elif isinstance(entity, adsk.fusion.ChamferFeature):
                #     info = analyze_chamfer_feature(entity)
                #     for body_token in info['affected_bodies']:
                #         if body_token in body_modifiers:
                #             body_modifiers[body_token]['chamfer'] = max(
                #                 body_modifiers[body_token]['chamfer'],
                #                 info['distance']
                #             )
                #         else:
                #             body_modifiers[body_token] = {'rounding': 0, 'chamfer': info['distance']}

                elif isinstance(entity, adsk.fusion.Sketch):
                    pass

            except Exception as e:
                scad_code.append(f"// Error analyzing {feature_name}: {str(e)}")

        # PASS 2: Generate SCAD code with modifiers applied
        current_ops = {'union': [], 'difference': [], 'intersection': []}

        for idx, (entity, feature_name, info, feature_type) in enumerate(features_data):
            try:
                body_token = feature_to_bodies.get(idx)
                modifiers = body_modifiers.get(body_token, {'rounding': 0, 'chamfer': 0})
                rounding = modifiers['rounding']
                chamfer = modifiers['chamfer']

                if feature_type == 'extrude':
                    code = generate_extrude_scad(info, feature_name,
                                                 rounding=rounding, chamfer=chamfer)

                    if info['operation'] == 'new' or info['operation'] == 'union':
                        current_ops['union'].extend(code)
                    elif info['operation'] == 'difference':
                        current_ops['difference'].extend(code)
                    elif info['operation'] == 'intersection':
                        current_ops['intersection'].extend(code)

                elif feature_type == 'revolve':
                    code = generate_revolve_scad(info, feature_name)
                    current_ops['union'].extend(code)

                elif feature_type == 'hole':
                    code = generate_hole_scad(info, feature_name)
                    current_ops['difference'].extend(code)

            except Exception as e:
                scad_code.append(f"// Error generating {feature_name}: {str(e)}")

        # Combine boolean operations
        if current_ops['difference']:
            scad_code.append("difference() {")
            if current_ops['union']:
                scad_code.append("    union() {")
                for line in current_ops['union']:
                    scad_code.append(f"        {line}")
                scad_code.append("    }")
            for line in current_ops['difference']:
                scad_code.append(f"    {line}")
            scad_code.append("}")
        elif current_ops['union']:
            if len(current_ops['union']) > 3:
                scad_code.append("union() {")
                for line in current_ops['union']:
                    scad_code.append(f"    {line}")
                scad_code.append("}")
            else:
                scad_code.extend(current_ops['union'])

        return scad_code

    def export(self) -> str:
        """Generate complete OpenSCAD file content"""
        all_lines = []

        all_lines.extend(generate_header())

        self.extract_parameters()
        all_lines.extend(generate_parameters_section(self.parameters))

        all_lines.extend([
            "// ============================================",
            "// Geometry (exported from Fusion 360 features)",
            "// ============================================",
            ""
        ])

        geometry_code = self.process_timeline()
        all_lines.extend(geometry_code)

        return '\n'.join(all_lines)

    def export_debug_json(self) -> dict:
        """Export detailed debug information from the Fusion 360 API"""
        debug_data = {
            'design_name': self.design.rootComponent.name,
            'parameters': {},
            'features': [],
            'bodies': [],
            'sketches': []
        }

        # Export parameters
        params = self.design.userParameters
        for i in range(params.count):
            param = params.item(i)
            debug_data['parameters'][param.name] = {
                'value': param.value,
                'value_mm': param.value * CM_TO_MM,
                'unit': param.unit,
                'expression': param.expression,
                'comment': param.comment
            }

        # Export timeline features
        timeline = self.design.timeline
        for i in range(timeline.count):
            item = timeline.item(i)
            entity = item.entity
            if entity is None:
                continue

            feature_data = {
                'index': i,
                'name': item.name if hasattr(item, 'name') else f'feature_{i}',
                'type': type(entity).__name__,
                'details': {}
            }

            try:
                if isinstance(entity, adsk.fusion.ExtrudeFeature):
                    profiles = entity.profile
                    profile = profiles if isinstance(profiles, adsk.fusion.Profile) else (profiles.item(0) if profiles.count > 0 else None)

                    if profile:
                        sketch = profile.parentSketch
                        if sketch:
                            transform = sketch.transform
                            origin = sketch.origin

                            feature_data['details']['sketch_name'] = sketch.name
                            feature_data['details']['sketch_origin'] = {
                                'x': origin.x * CM_TO_MM,
                                'y': origin.y * CM_TO_MM,
                                'z': origin.z * CM_TO_MM
                            }

                            if transform:
                                cs = transform.getAsCoordinateSystem()
                                origin_pt, x_axis, y_axis, z_axis = cs

                                feature_data['details']['transform'] = {
                                    'origin': {'x': origin_pt.x, 'y': origin_pt.y, 'z': origin_pt.z},
                                    'x_axis': {'x': x_axis.x, 'y': x_axis.y, 'z': x_axis.z},
                                    'y_axis': {'x': y_axis.x, 'y': y_axis.y, 'z': y_axis.z},
                                    'z_axis': {'x': z_axis.x, 'y': z_axis.y, 'z': z_axis.z}
                                }

                            ref_plane = sketch.referencePlane
                            if ref_plane:
                                feature_data['details']['reference_plane'] = str(type(ref_plane).__name__)
                                if hasattr(ref_plane, 'geometry'):
                                    plane_geom = ref_plane.geometry
                                    if hasattr(plane_geom, 'normal'):
                                        n = plane_geom.normal
                                        feature_data['details']['plane_normal'] = {'x': n.x, 'y': n.y, 'z': n.z}
                                    if hasattr(plane_geom, 'origin'):
                                        o = plane_geom.origin
                                        feature_data['details']['plane_origin'] = {'x': o.x, 'y': o.y, 'z': o.z}

                    extent_def = entity.extentOne
                    if isinstance(extent_def, adsk.fusion.DistanceExtentDefinition):
                        feature_data['details']['height_cm'] = extent_def.distance.value
                        feature_data['details']['height_mm'] = extent_def.distance.value * CM_TO_MM

                    try:
                        start_faces = entity.startFaces
                        if start_faces and start_faces.count > 0:
                            face = start_faces.item(0)
                            if hasattr(face, 'geometry') and hasattr(face.geometry, 'normal'):
                                n = face.geometry.normal
                                feature_data['details']['start_face_normal'] = {'x': n.x, 'y': n.y, 'z': n.z}
                    except:
                        pass

                    try:
                        end_faces = entity.endFaces
                        if end_faces and end_faces.count > 0:
                            face = end_faces.item(0)
                            if hasattr(face, 'geometry') and hasattr(face.geometry, 'normal'):
                                n = face.geometry.normal
                                feature_data['details']['end_face_normal'] = {'x': n.x, 'y': n.y, 'z': n.z}
                    except:
                        pass

                    try:
                        bodies = entity.bodies
                        body_list = []
                        for b in range(bodies.count):
                            body = bodies.item(b)
                            bbox = body.boundingBox
                            body_list.append({
                                'name': body.name,
                                'bbox_min': {'x': bbox.minPoint.x * CM_TO_MM, 'y': bbox.minPoint.y * CM_TO_MM, 'z': bbox.minPoint.z * CM_TO_MM},
                                'bbox_max': {'x': bbox.maxPoint.x * CM_TO_MM, 'y': bbox.maxPoint.y * CM_TO_MM, 'z': bbox.maxPoint.z * CM_TO_MM}
                            })
                        feature_data['details']['bodies'] = body_list
                    except:
                        pass

                    op_map = {
                        0: 'JoinFeatureOperation',
                        1: 'CutFeatureOperation',
                        2: 'IntersectFeatureOperation',
                        3: 'NewBodyFeatureOperation',
                        4: 'NewComponentFeatureOperation'
                    }
                    feature_data['details']['operation'] = op_map.get(entity.operation, str(entity.operation))

                elif isinstance(entity, adsk.fusion.HoleFeature):
                    if entity.holeDiameter:
                        feature_data['details']['diameter'] = entity.holeDiameter.value * CM_TO_MM

                    types = {
                        0: 'SimpleHole', 1: 'CounterboreHole', 2: 'CountersinkHole'
                    }
                    feature_data['details']['hole_type'] = types.get(entity.holeType, str(entity.holeType))

                    if entity.position:
                        p = entity.position
                        feature_data['details']['position'] = {'x': p.x * CM_TO_MM, 'y': p.y * CM_TO_MM, 'z': p.z * CM_TO_MM}

                elif isinstance(entity, adsk.fusion.Sketch):
                    feature_data['details']['profile_count'] = entity.profiles.count
                    feature_data['details']['curve_count'] = entity.sketchCurves.count

            except Exception as e:
                feature_data['error'] = str(e)

            debug_data['features'].append(feature_data)

        # Export bodies from root component
        try:
            bodies = self.design.rootComponent.bRepBodies
            for i in range(bodies.count):
                body = bodies.item(i)
                bbox = body.boundingBox
                debug_data['bodies'].append({
                    'name': body.name,
                    'bbox_min': {'x': bbox.minPoint.x * CM_TO_MM, 'y': bbox.minPoint.y * CM_TO_MM, 'z': bbox.minPoint.z * CM_TO_MM},
                    'bbox_max': {'x': bbox.maxPoint.x * CM_TO_MM, 'y': bbox.maxPoint.y * CM_TO_MM, 'z': bbox.maxPoint.z * CM_TO_MM}
                })
        except:
            pass

        return debug_data
