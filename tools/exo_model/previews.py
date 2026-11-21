"""Render EXO presentation views headlessly from the currently loaded blend.

blender -b exo_model.blend --python previews.py -- [front|back|left|three_quarter|crouch|elbow110|solo|all]
The scene is not saved; reference material substitutions and studio objects are temporary.
"""
import math
import os
import sys
import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import review

VIEWS = {
    'front': ('rest', (0, -1, .07), False),
    'back': ('rest', (0, 1, .07), False),
    'left': ('rest', (1, 0, .07), False),
    'three_quarter': ('rest', (1, -1.55, .18), False),
    'crouch': ('crouch', (1, -1.55, .18), False),
    'elbow110': ('elbow110', (1, -1.55, .18), False),
    'solo': ('rest', (1, 1.55, .28), True),
}


def has_valid_image_material(obj):
    """Only retain reference materials when their image maps are available."""
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type != 'TEX_IMAGE' or not node.image:
                continue
            img = node.image
            if img.packed_file or img.source == 'GENERATED':
                return True
            if img.filepath and os.path.isfile(bpy.path.abspath(img.filepath, library=img.library)):
                return True
    return False


def fabric_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None) or nodes.new('ShaderNodeBsdfPrincipled')
    output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None) or nodes.new('ShaderNodeOutputMaterial')
    mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = .88
    noise_color = nodes.new('ShaderNodeTexNoise')
    noise_color.inputs['Scale'].default_value = 75
    noise_color.inputs['Detail'].default_value = 3
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = tuple(c * .68 for c in color) + (1,)
    ramp.color_ramp.elements[1].color = tuple(min(c * 1.22, 1) for c in color) + (1,)
    mat.node_tree.links.new(noise_color.outputs['Fac'], ramp.inputs['Fac'])
    mat.node_tree.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    # Subtle woven-fabric breakup, kept neutral so the frame remains legible.
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 550
    noise.inputs['Detail'].default_value = 2
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .12
    bump.inputs['Distance'].default_value = .001
    mat.node_tree.links.new(noise.outputs['Fac'], bump.inputs['Height'])
    mat.node_tree.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def area(name, location, target, power, size, color):
    light = bpy.data.lights.new(name, 'AREA')
    light.energy = power
    light.shape = 'DISK'
    light.size = size
    light.color = color
    obj = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    return obj


def install_reference_materials():
    """Add neutral olive/tan fabric where clothing has no accessible image maps.

    This changes only REF_top and REF_pants; call before saving if desired.
    """
    for ref, color in [('REF_top', (.145, .16, .115)), ('REF_pants', (.19, .17, .125))]:
        obj = bpy.data.objects.get(ref)
        if obj and not has_valid_image_material(obj):
            names = ['PREVIEW_' + ref, 'PREVIEW_' + ref + '_leather', 'PREVIEW_' + ref + '_sole']
            colors = [color, (.038, .043, .039), (.018, .020, .019)]
            mats = [bpy.data.materials.get(n) or fabric_material(n, c) for n, c in zip(names, colors)]
            obj.data.materials.clear()
            for mat in mats:
                obj.data.materials.append(mat)
            adjacency = [[] for _ in obj.data.vertices]
            for edge in obj.data.edges:
                a, b = edge.vertices
                adjacency[a].append(b)
                adjacency[b].append(a)
            island_material = [-1] * len(adjacency)
            for start in range(len(adjacency)):
                if island_material[start] != -1:
                    continue
                stack = [start]
                island_material[start] = 0
                component = []
                while stack:
                    i = stack.pop()
                    component.append(i)
                    for j in adjacency[i]:
                        if island_material[j] == -1:
                            island_material[j] = 0
                            stack.append(j)
                if ref == 'REF_pants':
                    max_z = max(obj.data.vertices[i].co.z for i in component)
                    index = 2 if max_z < .032 else 1 if max_z < .11 else 0
                else:
                    max_y = max(obj.data.vertices[i].co.y for i in component)
                    index = 1 if max_y < -.329 else 0
                for i in component:
                    island_material[i] = index
            for poly in obj.data.polygons:
                poly.material_index = island_material[poly.vertices[0]]
        if obj:
            for poly in obj.data.polygons:
                poly.use_smooth = True


def setup():
    scene = bpy.context.scene
    for obj in bpy.data.objects:
        if obj.type in {'LIGHT', 'CAMERA'}:
            obj.hide_render = True
        elif obj.type == 'MESH':
            obj.hide_render = not (obj.name.startswith('EXO_') or obj.name in {'REF_pants', 'REF_top'})
    install_reference_materials()
    world = bpy.data.worlds.new('PREVIEW_studio_world')
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == 'BACKGROUND'), None) or world.node_tree.nodes.new('ShaderNodeBackground')
    output = next((n for n in world.node_tree.nodes if n.type == 'OUTPUT_WORLD'), None) or world.node_tree.nodes.new('ShaderNodeOutputWorld')
    world.node_tree.links.new(bg.outputs['Background'], output.inputs['Surface'])
    bg.inputs['Color'].default_value = (.32, .30, .28, 1)
    bg.inputs['Strength'].default_value = .7
    scene.world = world
    scene.render.engine = 'CYCLES'
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 800
    scene.render.resolution_y = 950
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = 'AgX'
    except TypeError:
        pass
    scene.view_settings.look = 'AgX - Medium High Contrast' if 'AgX - Medium High Contrast' in [i.name for i in scene.view_settings.bl_rna.properties['look'].enum_items] else scene.view_settings.look
    camera = bpy.data.cameras.new('PREVIEW_camera')
    camera.type = 'ORTHO'
    camera.lens = 50
    obj = bpy.data.objects.new('PREVIEW_camera', camera)
    scene.collection.objects.link(obj)
    scene.camera = obj
    return obj


def bounds_points():
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or obj.hide_render or obj.name.startswith('PREVIEW_'):
            continue
        evaluated = obj.evaluated_get(depsgraph)
        points.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
    if not points:
        raise RuntimeError('No visible EXO or reference meshes found')
    return points


def render(name, camera, save_png=True):
    pose, direction, solo = VIEWS[name]
    review.set_pose(pose)
    for ref in ('REF_top', 'REF_pants'):
        obj = bpy.data.objects.get(ref)
        if obj:
            obj.hide_render = solo
    bpy.context.view_layer.update()
    points = bounds_points()
    lower = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    upper = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    target = (lower + upper) / 2
    floor = bpy.data.objects.get('PREVIEW_floor')
    if floor is None:
        bpy.ops.mesh.primitive_plane_add(size=200)
        floor = bpy.context.object
        floor.name = 'PREVIEW_floor'
        material = bpy.data.materials.new('PREVIEW_floor_material')
        material.diffuse_color = (.29, .275, .255, 1)
        material.use_nodes = True
        shader = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        shader.inputs['Base Color'].default_value = (.29, .275, .255, 1)
        shader.inputs['Roughness'].default_value = .9
        floor.data.materials.append(material)
    floor.hide_render = False
    floor.location.z = lower.z - .001
    direction = Vector(direction).normalized()
    camera.location = target + direction * 5
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    rotation = camera.rotation_euler.to_matrix()
    right, up = rotation.col[0], rotation.col[1]
    h = [p.dot(right) for p in points]
    v = [p.dot(up) for p in points]
    aspect = bpy.context.scene.render.resolution_x / bpy.context.scene.render.resolution_y
    camera.data.ortho_scale = max(max(v)-min(v), (max(h)-min(h))/aspect) * 1.16
    # Recenter the actual projected extents, including asymmetric posed limbs.
    shift = right * ((max(h)+min(h))/2 - target.dot(right)) + up * ((max(v)+min(v))/2 - target.dot(up))
    camera.location += shift
    for obj in list(bpy.data.objects):
        if obj.name.startswith('PREVIEW_light'):
            bpy.data.objects.remove(obj, do_unlink=True)
    # Lights follow the camera, maintaining readable highlights in every view.
    right = Vector(right)
    area('PREVIEW_light_key', target + direction * 3 + right * -2 + Vector((0, 0, 3)), target, 170, 3.2, (1.0, .93, .84))
    area('PREVIEW_light_fill', target + direction * 2.5 + right * 2 + Vector((0, 0, .8)), target, 90, 3.0, (.78, .86, 1.0))
    area('PREVIEW_light_rim', target - direction * 2 + right * 1.5 + Vector((0, 0, 2.4)), target, 200, 2.4, (.86, .92, 1.0))
    scene = bpy.context.scene
    os.makedirs(os.path.join(ROOT, 'previews'), exist_ok=True)
    scene.render.filepath = os.path.join(ROOT, 'previews', name + '.png')
    if save_png:
        bpy.ops.render.render(write_still=True)
        print('PREVIEW_WRITTEN', scene.render.filepath, flush=True)


def main():
    args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    requested = args[0] if args else 'all'
    if requested != 'all' and requested not in VIEWS:
        raise ValueError('Preview must be one of: all, ' + ', '.join(VIEWS))
    camera = setup()
    for name in VIEWS if requested == 'all' else [requested]:
        render(name, camera)


if __name__ == '__main__':
    main()
