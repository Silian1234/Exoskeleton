"""Pose and geometric QA for the exoskeleton; run with Blender, never saves a blend.

Example: blender -b exo_model.blend --python review.py
Measurements are geometric indicators, not a substitute for inspecting renders.
"""
import bpy
import json
import math
import os
from collections import Counter
from mathutils import Vector, Quaternion, Matrix
from mathutils.bvhtree import BVHTree

ARM = bpy.data.objects['EFT_Bind']
# Capture the file's state and restore it on exit. All test poses start at identity.
_ORIGINAL = {p.name: (p.matrix_basis.copy(), p.rotation_mode) for p in ARM.pose.bones}
_ORIGINAL_POSE_POSITION = ARM.data.pose_position
POSES = ('rest', 'crouch', 'knee120', 'elbow110', 'down60', 'twist30')


def restore_pose():
    for name, (matrix, mode) in _ORIGINAL.items():
        ARM.pose.bones[name].rotation_mode = mode
        ARM.pose.bones[name].matrix_basis = matrix
    ARM.data.pose_position = _ORIGINAL_POSE_POSITION
    bpy.context.view_layer.update()


def _world_head(name):
    return ARM.matrix_world @ ARM.data.bones[name].head_local


def _rotate(name, axis_world, degrees):
    bone = ARM.pose.bones[name]
    # Account for parent pose so the desired axis is expressed in pose-bone basis.
    parent_rotation = bone.parent.matrix.to_quaternion() if bone.parent else Quaternion()
    rest_rotation = bone.bone.matrix_local.to_quaternion()
    if bone.parent:
        rest_rotation = bone.parent.bone.matrix_local.to_quaternion().inverted() @ rest_rotation
    world_rotation = ARM.matrix_world.to_quaternion() @ parent_rotation @ rest_rotation
    axis_local = world_rotation.inverted() @ axis_world.normalized()
    bone.rotation_mode = 'QUATERNION'
    bone.rotation_quaternion = Quaternion(axis_local, math.radians(degrees))
    bpy.context.view_layer.update()


def set_pose(name):
    if name not in POSES:
        raise ValueError('Unknown pose: ' + str(name))
    ARM.data.pose_position = 'POSE'
    for bone in ARM.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    forward = Vector((0, -1, 0))
    for side in ('L', 'R'):
        prefix = 'Base Human' + side
        thigh = _world_head(prefix + 'Calf') - _world_head(prefix + 'Thigh1')
        calf = _world_head(prefix + 'Foot') - _world_head(prefix + 'Calf')
        upper = _world_head(prefix + 'Forearm1') - _world_head(prefix + 'Upperarm')
        fore = _world_head(prefix + 'Palm') - _world_head(prefix + 'Forearm1')
        if name == 'crouch':
            _rotate(prefix + 'Thigh1', thigh.cross(forward), 60)
            _rotate(prefix + 'Calf', calf.cross(forward), -95)
        elif name == 'knee120':
            _rotate(prefix + 'Calf', calf.cross(forward), -120)
        elif name == 'elbow110':
            # Rotate the forward-pointing forearm upward around the outward
            # lateral elbow axle, with mirrored axes on opposite sides.
            axis = fore.cross(Vector((0, 0, 1)))
            _rotate(prefix + 'Forearm1', axis, 110)
        elif name == 'down60':
            _rotate(prefix + 'Upperarm', upper.cross(Vector((0, 0, -1))), 60)
    if name == 'crouch':
        # Cancel accumulated leg rotation at each ankle: the foot keeps its
        # bind orientation, including the original toe-to-heel slope.
        for side in ('L', 'R'):
            foot = ARM.pose.bones['Base Human' + side + 'Foot']
            desired = foot.bone.matrix_local.to_quaternion()
            parent = foot.parent.matrix.to_quaternion()
            relative = foot.parent.bone.matrix_local.to_quaternion().inverted() @ desired
            foot.rotation_mode = 'QUATERNION'
            foot.rotation_quaternion = (parent @ relative).inverted() @ desired
            bpy.context.view_layer.update()
        # Lower pelvis until the mean foot-bone head returns to bind height.
        foot_names = ['Base HumanLFoot', 'Base HumanRFoot']
        delta_z = sum(_world_head(n).z - (ARM.matrix_world @ ARM.pose.bones[n].head).z for n in foot_names) / 2
        delta_arm = ARM.matrix_world.inverted().to_3x3() @ Vector((0, 0, delta_z))
        for bone in ARM.pose.bones:
            if not bone.parent:
                bone.matrix = Matrix.Translation(delta_arm) @ bone.matrix
        bpy.context.view_layer.update()
    if name == 'twist30':
        # Collar bones are separate roots in this scene, so rotate them
        # around the spine pivot along with their descendants.
        pivot = ARM.data.bones['Base HumanSpine2'].head_local.copy()
        axis = ARM.matrix_world.to_quaternion().inverted() @ Vector((0, 0, 1))
        transform = Matrix.Translation(pivot) @ Quaternion(axis, math.radians(30)).to_matrix().to_4x4() @ Matrix.Translation(-pivot)
        _rotate('Base HumanSpine2', Vector((0, 0, 1)), 30)
        for side in ('L', 'R'):
            collar = ARM.pose.bones['Base Human' + side + 'Collarbone']
            if collar.parent is None:
                collar.matrix = transform @ collar.matrix
        bpy.context.view_layer.update()
    bpy.context.view_layer.update()


def _mesh(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    mesh.calc_loop_triangles()
    verts = [evaluated.matrix_world @ v.co for v in mesh.vertices]
    triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
    evaluated.to_mesh_clear()
    return verts, triangles


def _topology(triangles):
    edges = Counter()
    directed = Counter()
    for tri in triangles:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            edges[tuple(sorted((a, b)))] += 1
            directed[(a, b)] += 1
    boundary = sum(n == 1 for n in edges.values())
    nonmanifold = sum(n > 2 for n in edges.values())
    inconsistent = sum(n == 2 and (directed[(a, b)] != 1 or directed[(b, a)] != 1)
                       for (a, b), n in edges.items())
    return {'boundary_edges': boundary, 'nonmanifold_edges': nonmanifold,
            'inconsistent_winding_edges': inconsistent,
            'closed_consistently_wound': not (boundary or nonmanifold or inconsistent)}


def _percentile(data, q):
    if not data:
        return None
    data = sorted(data)
    return round(data[round((len(data) - 1) * q)] * 1000, 3)


def measure():
    """Measure both evaluated LODs vs evaluated clothing in world space, in millimetres.

    Signed side tests use nearest triangle normals, which are only local indications
    on open clothing; surface overlap counts give direct intersection evidence.
    Clearance samples include vertices, edge midpoints and triangle centroids.
    """
    bpy.context.view_layer.update()
    import sys
    sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
    from proximity import Garment,Pair
    import numpy as np
    depsgraph = bpy.context.evaluated_depsgraph_get()
    refs = []
    topology = {}
    garment_vertices=[];garment_triangles=[]
    for name in ('REF_top', 'REF_pants'):
        verts, tris = _mesh(bpy.data.objects[name], depsgraph)
        topology[name] = _topology(tris)
        garment_triangles.extend(tuple(i+len(garment_vertices) for i in tri) for tri in tris)
        garment_vertices.extend(verts)
        refs.append((name, BVHTree.FromPolygons(verts, tris, all_triangles=True)))
    garment=Garment(garment_vertices,garment_triangles)
    objects = sorted((o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith(('EXO_', 'EXO1_'))), key=lambda o:o.name)
    result = {'clothing_topology': topology, 'parts': {}}
    for obj in objects:
        verts, tris = _mesh(obj, depsgraph)
        if not verts or not tris:
            continue
        tree = BVHTree.FromPolygons(verts, tris, all_triangles=True)
        overlaps = {name: len(tree.overlap(ref)) for name, ref in refs}
        points=np.asarray(verts)
        pair=Pair(garment,points,tris,.026)
        gap=min((d for _,_,d in pair.features(points,.026)),default=None)
        if any(overlaps.values()):
            gap=0.
        # Vertices plus centroids give good coverage; midpoint sampling catches edges.
        samples = list(verts)
        seen = set()
        for tri in tris:
            a, b, c = (verts[i] for i in tri)
            samples.append((a + b + c) / 3)
            for i, j in zip(tri, tri[1:] + tri[:1]):
                edge = tuple(sorted((i, j)))
                if edge not in seen:
                    seen.add(edge)
                    samples.append((verts[i] + verts[j]) / 2)
        distances = []
        negative = 0
        for point in samples:
            hits = [(name, tree_ref.find_nearest(point)) for name, tree_ref in refs]
            hits = [(name, hit) for name, hit in hits if hit[0] is not None]
            if not hits:
                continue
            _, (location, normal, _, distance) = min(hits, key=lambda item: item[1][3])
            distances.append(distance)
            if (point - location).dot(normal) < -1e-6:
                negative += 1
        result['parts'][obj.name] = {
            'lod': 'LOD1' if obj.name.startswith('EXO1_') else 'LOD0',
            'sample_count': len(distances),
            'closest_surface_gap_mm': round(float(gap)*1000,3) if gap is not None else None,
            'samples_5_to_25_mm_percent': round(100 * sum(.005 <= d <= .025 for d in distances) / len(distances), 2) if distances else None,
            'distance_mm': {'min': _percentile(distances, 0), 'p05': _percentile(distances, .05),
                            'median': _percentile(distances, .5), 'p95': _percentile(distances, .95),
                            'max': _percentile(distances, 1)},
            'nearest_normal_negative_samples': negative,
            'surface_intersection_triangle_pairs': overlaps,
        }
    return result


def main():
    result = {'units': 'millimetres',
              'caveat': 'Open or inconsistently wound clothing does not define a reliable inside; nearest-normal negative counts are indications only. Intersection pairs are direct surface crossings. Sampling does not prove absence of penetration.',
              'poses': {}}
    try:
        for name in POSES:
            set_pose(name)
            result['poses'][name] = measure()
            print('QA', name, len(result['poses'][name]['parts']), 'parts', flush=True)
        path = os.path.join(os.path.dirname(bpy.data.filepath), 'qa_metrics.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print('QA metrics saved:', path, flush=True)
    finally:
        restore_pose()


if __name__ == '__main__':
    main()

