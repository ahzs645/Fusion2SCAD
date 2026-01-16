#Author: Fusion2SCAD
#Description: Utility functions for OpenSCAD export

import math

# Conversion factor: Fusion 360 uses cm internally, OpenSCAD typically uses mm
CM_TO_MM = 10.0


class WarningsCollector:
    """Collects warnings during SCAD generation for consolidated reporting."""

    def __init__(self):
        self.warnings = []
        self.errors = []

    def add_warning(self, feature_name: str, message: str, category: str = "constraint"):
        """Add a warning message.

        Args:
            feature_name: Name of the feature (e.g., "Extrude1")
            message: Warning description
            category: Type of warning (constraint, skip, info)
        """
        self.warnings.append({
            'feature': feature_name,
            'message': message,
            'category': category
        })

    def add_error(self, feature_name: str, message: str):
        """Add an error message (feature was skipped)."""
        self.errors.append({
            'feature': feature_name,
            'message': message
        })

    def has_issues(self) -> bool:
        """Check if there are any warnings or errors."""
        return len(self.warnings) > 0 or len(self.errors) > 0

    def generate_summary(self) -> list:
        """Generate SCAD comment lines summarizing all issues.

        Returns:
            List of comment strings for the SCAD file header
        """
        if not self.has_issues():
            return []

        lines = [
            "// ============================================",
            "// WARNINGS & NOTES",
            "// ============================================"
        ]

        # Group by category
        if self.errors:
            lines.append("//")
            lines.append("// ERRORS (features skipped):")
            for err in self.errors:
                lines.append(f"//   - {err['feature']}: {err['message']}")

        constraint_warnings = [w for w in self.warnings if w['category'] == 'constraint']
        if constraint_warnings:
            lines.append("//")
            lines.append("// CONSTRAINT ADJUSTMENTS:")
            for warn in constraint_warnings:
                lines.append(f"//   - {warn['feature']}: {warn['message']}")

        other_warnings = [w for w in self.warnings if w['category'] not in ('constraint',)]
        if other_warnings:
            lines.append("//")
            lines.append("// OTHER NOTES:")
            for warn in other_warnings:
                lines.append(f"//   - {warn['feature']}: {warn['message']}")

        lines.append("//")
        lines.append("")
        return lines


def sanitize_name(name: str) -> str:
    """Convert Fusion parameter name to valid OpenSCAD variable name"""
    sanitized = ''.join(c if c.isalnum() or c == '_' else '_' for c in name)
    if sanitized and sanitized[0].isdigit():
        sanitized = '_' + sanitized
    return sanitized.lower()


def format_value(value: float, precision: int = 4) -> str:
    """Format a numeric value for OpenSCAD output"""
    if abs(value - round(value)) < 0.0001:
        return str(int(round(value)))
    return f"{value:.{precision}f}".rstrip('0').rstrip('.')


def normal_to_rotation(nx: float, ny: float, nz: float) -> tuple:
    """Convert a normal vector to rotation angles (rx, ry, rz) in degrees.
    This rotates the Z-axis to align with the given normal."""
    length = math.sqrt(nx*nx + ny*ny + nz*nz)
    if length < 0.0001:
        return (0, 0, 0)

    nx, ny, nz = nx/length, ny/length, nz/length

    # Rotation around Y-axis (pitch) to tilt Z toward X
    ry = math.degrees(math.asin(-nx))

    # Rotation around X-axis (roll) to tilt Z toward Y
    rx = math.degrees(math.atan2(ny, nz))

    return (rx, ry, 0)


def get_rotation_matrix_from_axis(axis) -> list:
    """Construct a rotation matrix (4x4) aligning Z to the given axis.

    Args:
        axis: An adsk.core.Vector3D object

    Returns:
        4x4 rotation matrix as nested list
    """
    import adsk.core

    # Ensure normalized
    z_vec = axis.copy()
    z_vec.normalize()

    # Pick arbitrary vector not parallel to Z
    if abs(z_vec.x) < 0.9:
        ref = adsk.core.Vector3D.create(1, 0, 0)
    else:
        ref = adsk.core.Vector3D.create(0, 1, 0)

    # Construct basis vectors
    x_vec = ref.crossProduct(z_vec)
    x_vec.normalize()

    y_vec = z_vec.crossProduct(x_vec)
    y_vec.normalize()

    # Build 4x4 matrix (basis vectors as columns)
    return [
        [x_vec.x, y_vec.x, z_vec.x, 0],
        [x_vec.y, y_vec.y, z_vec.y, 0],
        [x_vec.z, y_vec.z, z_vec.z, 0],
        [0, 0, 0, 1]
    ]
