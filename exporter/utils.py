#Author: Fusion2SCAD
#Description: Utility functions for OpenSCAD export

import math

# Conversion factor: Fusion 360 uses cm internally, OpenSCAD typically uses mm
CM_TO_MM = 10.0


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
