# Fusion2SCAD AI Agent Instructions

## Project Overview
Fusion2SCAD is a Fusion 360 add-in that exports parametric CAD designs to OpenSCAD with BOSL2 library support. It translates Fusion 360's timeline-based features (extrusions, revolves, fillets, chamfers) into clean OpenSCAD/BOSL2 code.

## Architecture

### Two-Phase Processing Model
The exporter uses a **two-pass timeline analysis**:
1. **Pass 1**: Collect features and associate modifiers with bodies using `body.entityToken`
2. **Pass 2**: Generate SCAD code with modifiers (fillets/chamfers) applied to their parent shapes

This pattern in [`process_timeline()`](Fusion2SCAD.py#L773-L920) ensures fillets/chamfers applied after extrudes are correctly converted to BOSL2 `rounding=` or `chamfer=` parameters on the base shape.

### Key Modules
- **[Fusion2SCAD.py](Fusion2SCAD.py)**: Main exporter (`SCADExporter` class) and Fusion 360 UI integration
- **[profile_utils.py](profile_utils.py)**: Sketch profile extraction and shape recognition (circles, rectangles, rounded rectangles, complex polygons)

### Coordinate System Conversion
- Fusion 360 uses **centimeters** internally; OpenSCAD uses **millimeters**
- Apply `CM_TO_MM = 10.0` conversion to all dimensional values
- Sketch transforms use `multmatrix()` for 3D positioning (see [`_generate_transform_prefix()`](Fusion2SCAD.py#L561-L620))

### Shape Recognition Pipeline
1. [`detect_shape_type()`](profile_utils.py#L261-L350) identifies circles, rectangles, rounded rectangles from sketch profiles
2. Generates clean BOSL2 primitives: `cyl()`, `cuboid()`, `cuboid(rounding=...)`
3. Falls back to `linear_extrude()` + `polygon()` for complex profiles using [`extract_profile_polygon()`](profile_utils.py#L105-L195)

## Development Patterns

### Parameter Extraction
User parameters from Fusion 360 are sanitized (spaces→underscores, no leading digits) in [`extract_parameters()`](Fusion2SCAD.py#L59-L75). Match parameter expressions from feature definitions using `fusion_expression` to link values.

### Feature Analysis Methods
Each feature type has an `analyze_*_feature()` method that returns a normalized dict:
- [`analyze_extrude_feature()`](Fusion2SCAD.py#L214-L335): Extracts height, taper, sketch plane transform, profiles
- [`analyze_fillet_feature()`](Fusion2SCAD.py#L394-L416): Tracks `affected_bodies` set via entity tokens
- [`analyze_chamfer_feature()`](Fusion2SCAD.py#L418-L444): Similar to fillet tracking

### SCAD Code Generation
Generate methods return lists of strings for easy composition:
```python
def generate_extrude_scad(self, feature_info: dict, feature_name: str, 
                         rounding: float = 0, chamfer: float = 0) -> list:
    lines = []
    lines.append(f"// {feature_name}")
    # ... build BOSL2 code
    return lines
```

### Boolean Operation Assembly
Operations are grouped in [`process_timeline()`](Fusion2SCAD.py#L858-L920):
```python
current_ops = {'union': [], 'difference': [], 'intersection': []}
# ... collect features ...
if current_ops['union']:
    scad_code.append("union() {")
    # ... add union operations
```

## Fusion 360 API Patterns

### Timeline Iteration
```python
timeline = self.design.timeline
for i in range(timeline.count):
    item = timeline.item(i)
    entity = item.entity  # Can be ExtrudeFeature, FilletFeature, etc.
```

### Profile Handling
Profiles can be single objects or collections:
```python
profiles = feature.profile
if isinstance(profiles, adsk.fusion.Profile):
    profile_info = self._analyze_profile(profiles)
else:
    for i in range(profiles.count):
        profile = profiles.item(i)
```

### Body Token Tracking
Use `body.entityToken` (string) to associate features with bodies across timeline:
```python
for body in entity.bodies:
    token = body.entityToken
    body_modifiers[token] = {'rounding': 0, 'chamfer': 0}
```

## Testing & Debugging

### Debug JSON Export
Every export generates a `*_debug.json` file with raw Fusion 360 API data (parameters, sketch transforms, bounding boxes). Reference this when debugging transform issues.

### Test Output Location
Test files in [`test/`](test/) follow naming: `YYYY-MM-DD at HH.MM.SS AM/PM.scad` with matching `*_debug.json`.

## Common Tasks

### Adding New Feature Support
1. Add `isinstance()` check in [`process_timeline()`](Fusion2SCAD.py#L773-L920)
2. Create `analyze_<feature>_feature()` method returning normalized dict
3. Implement `generate_<feature>_scad()` returning list of SCAD lines
4. Update boolean operation routing based on `feature.operation`

### Improving Shape Recognition
Extend [`detect_shape_type()`](profile_utils.py#L261-L350) by checking `curves.count` and curve types. Add new shape types to `generate_bosl2_shape()`.

### Transform Debugging
Check `sketch_transform` dict in feature_info for full 4x4 matrix components. Verify coordinate system axes match expected Fusion 360 plane orientation.

## Dependencies
- **Fusion 360 API**: `adsk.core`, `adsk.fusion` (provided by Fusion environment)
- **BOSL2**: External OpenSCAD library (user must install separately)
- **Python**: Runs in Fusion 360's embedded Python (CPython-based)

## Installation Context
Add-in lives in Fusion 360's API/AddIns directory. Manifest: [`Fusion2SCAD.manifest`](Fusion2SCAD.manifest). Entry points: `run()` and `stop()` functions.
