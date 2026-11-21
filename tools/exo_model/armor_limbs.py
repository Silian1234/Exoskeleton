"""Rigid, curved titanium panels for the upper arm, forearm, thigh and shin."""

from math import cos, radians, sin

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import review


# Longitudinal station, minimum and maximum wrap angle. End stations
# narrow the plates, leaving the articulated ends and boot visible.
PAULDRON = (
    (.11, 0, 62), (.16, -24, 84), (.26, -27, 112),
    (.34, -18, 116), (.41, 12, 108), (.47, 40, 95),
)
VAMBRACE = (
    (.26, 43, 103), (.35, 29, 128), (.46, 15, 143),
    (.64, -1, 149), (.79, -12, 141), (.89, -3, 126),
)
THIGH = (
    (.285, -9, 49), (.315, -23, 65), (.36, -30, 72),
    (.41, -33, 74), (.47, -32, 72), (.55, -26, 64),
)
THIGH_LOWER = (
    (.773, -22, 57), (.801, -30, 64), (.846, -24, 59), (.895, -17, 46),
)
GREAVE = (
    (.12, -22, 57), (.19, -40, 75), (.33, -40, 79),
    (.45, -36, 78), (.55, -33, 73), (.64, -26, 64),
)

PARTS = (
    ('pauldron', 'Upperarm', 'Forearm1', 'REF_top', PAULDRON, .008),
    ('vambrace', 'Forearm1', 'Palm', 'REF_top', VAMBRACE, .007),
    ('thighArmor', 'Thigh1', 'Calf', 'REF_pants', THIGH, .008),
    ('thighLower', 'Thigh1', 'Calf', 'REF_pants', THIGH_LOWER, .007),
    ('greave', 'Calf', 'Foot', 'REF_pants', GREAVE, .008),
)


def _project(vector, axis):
    return (vector - axis * axis.dot(vector)).normalized()


def _reference_surfaces(armature):
    """Capture clothing in the QA poses and rigid transforms per plate bone."""
    result = {}
    arm_world = armature.matrix_world
    arm_inverse = arm_world.inverted()
    try:
        for pose in review.POSES:
            review.set_pose(pose)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            surfaces = {}
            for object_name in ('REF_top', 'REF_pants'):
                vertices, triangles = review._mesh(bpy.data.objects[object_name], depsgraph)
                surfaces[object_name] = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
            for side in ('L', 'R'):
                for bone, garment in {bone: garment for _, bone, _, garment, _, _ in PARTS}.items():
                    bone_name = 'Base Human' + side + bone
                    posed = armature.pose.bones[bone_name].matrix
                    rest = armature.data.bones[bone_name].matrix_local
                    transform = arm_world @ posed @ rest.inverted() @ arm_inverse
                    result.setdefault(bone_name, []).append((pose, surfaces[garment], transform))
    finally:
        review.restore_pose()
    return result


def _profile(center, direction, surfaces):
    radii = []
    for pose, tree, transform in surfaces:
        start = transform @ center
        ray = (transform.to_3x3() @ direction).normalized()
        # Shoot toward the bone from just beyond the garment. A narrow
        # radial window prevents the opposite arm or leg from being sampled.
        span = .174
        hit, normal, _, distance = tree.ray_cast(start + ray * span, -ray, span + .025)
        if hit is None or normal.dot(ray) < .035:
            if pose != 'rest':
                continue
            hit, normal, _, distance = tree.ray_cast(start, ray, span)
            if hit is None or normal.dot(ray) < .035:
                raise ValueError(f'Unable to fit limb plate at {tuple(center)} along {tuple(direction)}')
            radii.append(distance)
        else:
            radii.append(span - distance)

    rest = radii[0]
    return max(rest + .024, min(rest + .033, max(radii) + .021))


def _cuff_edge(name, side, row, last):
    """Return the target Z of a cuff-facing edge in the bind pose."""
    if (name in ('thighArmor', 'greave') and row == last):
        bone = 'thigh' if name == 'thighArmor' else 'calf'
        index = 1
    elif name == 'thighLower' and row == 0:
        bone = 'thigh'
        index = 0
    else:
        return None
    cuff = bpy.data.objects['EXO_' + bone + 'Cuff' + side]
    bounds = sorted((cuff.matrix_world @ Vector(corner)).z for corner in cuff.bound_box)
    return bounds[-1] + .006 if index else bounds[0] - .006


def _shell(armature, side, side_sign, part, surfaces):
    name, bone, end_bone, garment, stations, thickness = part
    prefix = 'Base Human' + side
    bone_name = prefix + bone
    head = armature.matrix_world @ armature.data.bones[bone_name].head_local
    tail = armature.matrix_world @ armature.data.bones[prefix + end_bone].head_local
    axis = (tail - head).normalized()

    if garment == 'REF_top':
        first = _project(Vector((0, 0, 1)), axis)
    else:
        first = _project(Vector((0, -1, 0)), axis)
    outer = Vector((side_sign, 0, 0))
    second = _project(outer - first * first.dot(outer), axis)

    directions = []
    centers = []
    offsets = []
    count = 6 if name=='thighLower' else 7

    for row_index, (station, left, right) in enumerate(stations):
        edge_z = _cuff_edge(name, side, row_index, len(stations) - 1)
        row_centers = []
        row_directions = []
        row_offsets = []
        for column in range(count):
            degrees = left + (right - left) * column / (count - 1)
            angle = radians(degrees)
            vector = first * cos(angle) + second * sin(angle)
            row_directions.append(vector)
            # The upper/medial corner is swept away from the trouser hip fold
            # while the outer cheek reaches farther up the carrier.
            relief = (max(0,1-(station-.285)/.23) *
                      max(0,min(1,(55-degrees)/64))*.050) if name=='thighArmor' else 0
            fitted_station=station+relief
            if name=='vambrace' and station>.60:
                # Saddle-shaped relief around the existing oblique wrist clamp.
                clamp_span=max(0,1-(abs(degrees-54)/64)**4)
                fitted_station-=.78*(station-.60)*clamp_span
            center = head.lerp(tail, fitted_station)
            radius = _profile(center, vector, surfaces[bone_name])
            if edge_z is not None:
                center += axis * ((edge_z - (center + vector * radius).z) / axis.z)
                radius = _profile(center, vector, surfaces[bone_name])
            row_centers.append(center)
            if bone == 'Forearm1':
                radius += .008
            if bone == 'Thigh1':
                radius += .006
                if .32 < station < .55 and 20 < degrees < 63:
                    radius += .008
            if bone == 'Upperarm' and .24 < station < .42 and 22 < degrees < 90:
                radius += .004
            if name == 'thighArmor' and .26 < station < .50 and degrees > 48:
                radius += .005
            if name == 'thighArmor' and station < .43 and degrees < 16:
                radius += .010
            row_offsets.append(radius)
        directions.append(row_directions)
        offsets.append(row_offsets)
        centers.append(row_centers)

    # The rigid plates soften small variations in the clothing silhouette.
    # Only raise low samples, so the deformation envelope remains covered.
    for _ in range(2):
        adjusted = []
        for y, row in enumerate(offsets):
            values = []
            for x, radius in enumerate(row):
                nearby = [
                    offsets[j][i]
                    for j, i in ((y-1, x), (y+1, x), (y, x-1), (y, x+1))
                    if 0 <= j < len(offsets) and 0 <= i < count
                ]
                values.append(max(radius, sum(nearby) / len(nearby) - .003))
            adjusted.append(values)
        offsets = adjusted

    rows = []
    for y, (row_centers, row_directions, row_offsets) in enumerate(zip(centers, directions, offsets)):
        edge_z = _cuff_edge(name, side, y, len(stations) - 1)
        row = []
        for center, direction, radius in zip(row_centers, row_directions, row_offsets):
            point = center + direction * radius
            if edge_z is not None:
                point += axis * ((edge_z - point.z) / axis.z)
            row.append(point)
        rows.append(row)
    normal = directions[len(directions)//2][count//2]
    return name + side, bone_name, rows, thickness, normal


def build(ctx):
    """Create the rigid limb panels via the shared armor panel builder."""
    armature = bpy.data.objects['EFT_Bind']
    surfaces = _reference_surfaces(armature)
    for side, sign in (('L', 1), ('R', -1)):
        for part in PARTS:
            name, bone, rows, thickness, normal = _shell(armature, side, sign, part, surfaces)
            ctx.panel(name, bone, rows, thickness=thickness, normal=normal)




