"""Torso cuirass, flank protection, collar and pelvis armor."""
import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import review


UPPER = 'Base HumanSpine3'
LOWER = 'Base HumanSpine2'
PELVIS = 'Base HumanPelvis'
NECK = 'Base HumanNeck'
NECK_YAW_ANGLES = range(-75, 76, 5)


class _PoseEnvelope:
    """Express evaluated garments in plate-bone coordinates for rigid-shell fitting."""

    def __init__(self):
        self.trees = {}
        rig = review.ARM
        world = rig.matrix_world
        inverse_world = world.inverted()
        try:
            for pose in review.POSES:
                review.set_pose(pose)
                depsgraph = bpy.context.evaluated_depsgraph_get()
                for garment in ('REF_top', 'REF_pants'):
                    vertices, tris = review._mesh(bpy.data.objects[garment], depsgraph)
                    for name in (UPPER, LOWER, PELVIS):
                        bone = rig.pose.bones[name]
                        to_bind = world @ bone.bone.matrix_local @ bone.matrix.inverted() @ inverse_world
                        self.trees[pose, garment, name] = BVHTree.FromPolygons(
                            [to_bind @ vertex for vertex in vertices], tris, all_triangles=True
                        )
        finally:
            review.restore_pose()

    def project(self, direction, center, bone, garment, span, clamp=.022, limb_filter=False):
        point = Vector(center)
        direction = Vector(direction)
        hits = []
        for pose in review.POSES:
            tree = self.trees[pose, garment, bone]
            reach = min(span, hits[0] + .032) if limb_filter and hits else span
            hit, _, _, _ = tree.ray_cast(point + direction * reach, -direction, reach)
            if hit is not None:
                hits.append((hit - point).dot(direction))
        if not hits:
            raise ValueError(f'No reference surface at {tuple(point)} against {garment}')
        # Shoulder/hip articulation can put a moving limb in the ray path.
        # The shell stays near its own torso/pelvis surface.
        return point + direction * min(max(hits), hits[0] + clamp)


def _span(a, b, steps):
    return [a + (b - a) * i / steps for i in range(steps + 1)]


def _torso_panel(ctx, fit, name, bone, sign, outline, thick, clearance, garment='REF_top',
                 span=.182, clamp=.022, edge_wrap=0):
    n = Vector((0, sign, 0))
    rows = []
    for left, right, z, edge in outline:
        row = []
        for i, x in enumerate(_span(left, right, 10)):
            # The top and bottom corners are swept to form the chamfered shell.
            across = (i - 5) / 5
            z_at_x = z + edge * across ** 4
            p = fit.project(n, (x, 0, z_at_x), bone, garment, span, clamp)
            row.append(p + n * (clearance + .003 * (1 - abs(across))) +
                       Vector((edge_wrap * across ** 3, 0, 0)))
        rows.append(row)
    ctx.panel(name, bone, rows, thickness=thick, normal=n)


def _symmetric(stations):
    return [(-width, width, z, chamfer) for z, width, chamfer in stations]


def _chest(ctx, fit):
    _torso_panel(ctx, fit, 'armorChest', UPPER, -1, _symmetric((
        (1.530, .087, -.011), (1.513, .124, -.017), (1.484, .157, -.011),
        (1.455, .166, -.008), (1.425, .163, -.003), (1.400, .157, 0),
        (1.375, .151, .001), (1.351, .141, .003), (1.330, .123, .007),
    )), .012, .028, edge_wrap=.005)
    _torso_panel(ctx, fit, 'armorAbdomen', LOWER, -1, _symmetric((
        (1.322, .110, .003), (1.304, .121, .001), (1.283, .121, 0),
        (1.244, .116, 0), (1.215, .114, 0), (1.185, .116, 0),
        (1.155, .112, .006), (1.134, .102, .010),
    )), .010, .026, edge_wrap=.002)


def _back(ctx, fit):
    _torso_panel(ctx, fit, 'armorBackYoke', UPPER, 1, _symmetric((
        (1.497, .092, -.007), (1.475, .129, -.011), (1.451, .149, -.006),
        (1.425, .149, -.004), (1.408, .114, .007),
    )), .012, .023)
    _torso_panel(ctx, fit, 'armorBackLumbar', LOWER, 1, _symmetric((
        (1.176, .103, .002), (1.167, .098, 0), (1.157, .080, .001), (1.147, .059, .006),
    )), .010, .021, clamp=.012)


def _flanks(ctx, fit):
    # Narrow under the sleeve, wider at the ribs, then taper above the belt.
    stations = (
        (1.325, -.088, -.063), (1.309, -.095, -.064), (1.288, -.100, -.068),
        (1.264, -.105, -.073), (1.240, -.107, -.078), (1.217, -.109, -.084),
        (1.192, -.109, -.091), (1.171, -.106, -.096),
    )
    for side, sign in (('L', 1), ('R', -1)):
        n = Vector((sign, 0, 0))
        rows = [
            [fit.project(n, (0, y, z), LOWER, 'REF_top', .190, .018, limb_filter=True) + n * .023
             for y in _span(front, back, 8)]
            for z, front, back in stations
        ]
        ctx.panel('armorFlank' + side, LOWER, rows, thickness=.007, normal=n)


def _rear_flanks(ctx, fit):
    # These guards wrap toward the shoulder behind the lowered sleeve.
    # Their medial edges leave the removable cells and spine keel exposed.
    stations = (
        (1.396, 43, 51), (1.375, 42, 51), (1.349, 40, 50),
        (1.324, 40, 50), (1.308, 38, 48),
        (1.287, 34, 45), (1.263, 31, 43), (1.240, 30, 41),
        (1.218, 29, 39), (1.199, 30, 38),
    )
    for side, sign in (('L', 1), ('R', -1)):
        rows = []
        for z, start, stop in stations:
            row = []
            for degrees in _span(start, stop, 6):
                theta = math.radians(degrees)
                d = Vector((sign * math.cos(theta), math.sin(theta), 0))
                p = fit.project(d, (0, .018, z), LOWER, 'REF_top', .220, .022, limb_filter=True)
                row.append(p + d * .023 + Vector((0, .004, 0)))
            rows.append(row)
        ctx.panel('armorFlankRear' + side, LOWER, rows, thickness=.010, normal=(sign, 1, 0))


def _neck_envelope(fit):
    """Include the jacket collar's deformation during head turning."""
    trees = [fit.trees[pose, 'REF_top', UPPER] for pose in review.POSES]
    try:
        for angle in NECK_YAW_ANGLES:
            if angle == 0:
                continue
            review.set_pose('rest')
            review._rotate(NECK, Vector((0, 0, 1)), angle)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            vertices, triangles = review._mesh(bpy.data.objects['REF_top'], depsgraph)
            trees.append(BVHTree.FromPolygons(vertices, triangles, all_triangles=True))
    finally:
        review.restore_pose()
    return trees


def _collar(ctx, fit):
    # Four segments share a smooth outline fitted to the rotating jacket collar.
    trees = _neck_envelope(fit)

    def direction(theta):
        return Vector((math.sin(theta), -math.cos(theta), 0))

    def station(theta, base_z):
        d = direction(theta)
        front = max(-d.y, 0)
        z = base_z + .006 * d.x ** 2 - .016 * front ** 2 - .004 * max(d.y, 0)
        z -= .066 * (d.x * front) ** 2
        return Vector((0, .058, z))

    def reach(theta, base_z):
        d = direction(theta)
        center = station(theta, base_z)
        reaches = []
        for tree in trees:
            point, _, _, _ = tree.ray_cast(center + d * .220, -d, .220)
            if point is not None:
                reaches.append((point - center).dot(d))
        return max(reaches, default=.077)

    bands = []
    angles = 96
    for height, spread in ((1.589, .748), (1.582, .762), (1.575, .762), (1.568, .748)):
        profile = [reach(i * math.tau / angles, height) for i in range(angles)]
        # Blend over the angular samples while retaining the local swept clearance.
        radii = [
            max(profile[i], sum(profile[(i+j) % angles] for j in range(-5, 6)) / 11)
            for i in range(angles)
        ]
        bands.append((height, spread, radii))

    for i, label in enumerate(('Front', 'Left', 'Rear', 'Right')):
        center = i * math.pi / 2
        rows = []
        for height, spread, radii in bands:
            row = []
            for angle in _span(center - spread, center + spread, 8):
                index = angle * angles / math.tau
                a = math.floor(index)
                f = index - a
                radius = (1 - f) * radii[a % angles] + f * radii[(a + 1) % angles]
                d = direction(angle)
                side_clearance = .010 * d.x ** 2
                throat_relief = .034 * (d.x * max(-d.y, 0)) ** 2
                row.append(station(angle, height) + d * (radius + .022 + side_clearance - throat_relief))
            rows.append(row)
        ctx.panel('armorGorget' + label, UPPER, rows, thickness=.006, normal=direction(center))


def _pelvis(ctx, fit):
    _torso_panel(ctx, fit, 'armorFauldFront', PELVIS, -1, _symmetric((
        (1.033, .055, -.006), (1.019, .069, -.002), (1.005, .060, 0),
        (.991, .045, .003), (.978, .031, .004), (.963, .021, .006),
        (.950, .012, .007),
    )), .007, .021, 'REF_pants', span=.38, clamp=.15)
    _torso_panel(ctx, fit, 'armorFauldRear', PELVIS, 1, _symmetric((
        (1.031, .072, -.010), (1.014, .105, -.008), (.991, .108, -.001),
        (.970, .098, .001), (.948, .073, .006), (.929, .049, .009),
    )), .007, .020, 'REF_pants', span=.235, clamp=.008)


def build(ctx):
    fit = _PoseEnvelope()
    _chest(ctx, fit)
    _back(ctx, fit)
    _flanks(ctx, fit)
    _rear_flanks(ctx, fit)
    _collar(ctx, fit)
    _pelvis(ctx, fit)


