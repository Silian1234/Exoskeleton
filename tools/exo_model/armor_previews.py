"""Render textured EXO previews headlessly without saving the open blend.

blender -b exo_t3a.blend --python armor_previews.py -- all
blender -b exo_t3a.blend --python armor_previews.py -- three_quarter --draft
blender -b --factory-startup --python armor_previews.py -- compare
"""
import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

FRONT_QUARTER = (1.3, -1.52, .14)
COMPARISON_VIEW = (.37, -1.52, .145)
VIEWS = {
    'front': ('rest', (0, -1, .055), False),
    'back': ('rest', (0, 1, .075), False),
    'left': ('rest', (1, 0, .07), False),
    'three_quarter': ('rest', FRONT_QUARTER, False),
    'crouch': ('crouch', (1.6, -1.05, .16), False),
    'elbow110': ('elbow110', (1.65, -1.2, .12), False),
    'solo': ('rest', (.92, -1.85, .25), True),
}
CLOTHING = ('REF_top', 'REF_pants')
DRAFT_VIEWS = {'down60': ('down60', FRONT_QUARTER, False)}


def load_tiers():
    """Append each assembly at the same scale, with its own reference and atlas."""
    direction = Vector(COMPARISON_VIEW).normalized()
    right = (-direction).to_track_quat('-Z', 'Y').to_matrix().col[0]
    tiers = (
        ('TIER 1', 'exo_model.blend', 'textures'),
        ('TIER 2', 'exo_t3.blend', 'textures_t3'),
        ('TIER 3', 'exo_t3a.blend', 'textures_t3a'),
    )
    labels = []
    models = []
    for index, (label, filename, atlas_dir) in enumerate(tiers):
        path = ROOT / filename
        offset = right * (index - 1) * 1.03
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            target.objects = [name for name in source.objects
                              if name in (*CLOTHING, 'EFT_Bind') or name.startswith('EXO_')]
        for obj in target.objects:
            bpy.context.scene.collection.objects.link(obj)
            if obj.parent is None:
                obj.location += offset
            obj.hide_set(False)
            obj.hide_render = False
            if obj.type == 'ARMATURE':
                obj.data.pose_position = 'REST'
            if obj.type != 'MESH':
                continue
            models.append(obj)
            if not obj.name.startswith('EXO_'):
                continue
            for slot in obj.material_slots:
                for node in slot.material.node_tree.nodes:
                    if node.type != 'TEX_IMAGE' or not node.image:
                        continue
                    image = node.image
                    image_path = ROOT / atlas_dir / Path(bpy.path.abspath(image.filepath)).name
                    if not image_path.is_file():
                        raise FileNotFoundError(image_path)
                    if not image.packed_file:
                        image.filepath = str(image_path)
                        image.reload()
        labels.append((label, offset))
    bpy.context.view_layer.update()
    return models, labels


def setup(draft, comparison):
    import previews

    camera = previews.setup()
    scene = bpy.context.scene
    scene.render.resolution_x = 2160 if comparison else 1120
    scene.render.resolution_y = 1320 if comparison else 1360
    scene.render.resolution_percentage = 50 if draft else 100
    scene.render.image_settings.color_mode = 'RGB'
    scene.cycles.samples = 12 if draft else 32
    scene.cycles.adaptive_threshold = .05 if draft else .025
    scene.view_settings.look = 'AgX - Medium High Contrast'
    world_bg = next(node for node in scene.world.node_tree.nodes if node.type == 'BACKGROUND')
    world_bg.inputs['Color'].default_value = (.38, .43, .53, 1)
    world_bg.inputs['Strength'].default_value = .65
    return camera


def evaluated_points(objects):
    """Use actual posed silhouettes for framing, including fingers or protrusions."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            transform = evaluated.matrix_world
            yield from (transform @ vertex.co for vertex in mesh.vertices)
        finally:
            evaluated.to_mesh_clear()


def add_floor(height):
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, height))
    floor = bpy.context.object
    floor.name = 'PREVIEW_floor'
    material = bpy.data.materials.new('PREVIEW_floor_material')
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value = (.275, .305, .35, 1)
    shader.inputs['Roughness'].default_value = .91
    floor.data.materials.append(material)
    return floor


def add_labels(labels, camera, direction, top):
    material = bpy.data.materials.new('PREVIEW_tier_label_material')
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value = (.37, .46, .55, 1)
    shader.inputs['Roughness'].default_value = .65
    up = camera.rotation_euler.to_matrix().col[1]
    for label, offset in labels:
        font = bpy.data.curves.new('PREVIEW_' + label, 'FONT')
        font.body = label
        font.size = .082
        font.align_x = 'CENTER'
        font.align_y = 'CENTER'
        obj = bpy.data.objects.new('PREVIEW_' + label, font)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = offset + up * (top + .120) + direction * .65
        obj.rotation_euler = camera.rotation_euler
        obj.data.materials.append(material)


def studio(camera, floor, model_points, direction, labels=()):
    import previews

    points = list(model_points)
    scene = bpy.context.scene
    direction = Vector(direction).normalized()
    camera.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
    rotation = camera.rotation_euler.to_matrix()
    right, up = rotation.col[0], rotation.col[1]
    x = [point.dot(right) for point in points]
    y = [point.dot(up) for point in points]
    z = [point.dot(direction) for point in points]
    top = max(y)
    top_margin = .24 if labels else .086
    bottom_margin = .115
    width = max(x) - min(x) + (.27 if labels else .13)
    height = top + top_margin - min(y) + bottom_margin
    target = right * ((max(x) + min(x)) / 2)
    target += up * ((top + top_margin + min(y) - bottom_margin) / 2)
    target += direction * ((max(z) + min(z)) / 2)
    aspect = scene.render.resolution_x / scene.render.resolution_y
    camera.data.ortho_scale = max(width, height * aspect) if aspect >= 1 else max(width / aspect, height)
    camera.location = target + direction * 6
    if labels:
        add_labels(labels, camera, direction, top)

    floor.location.z = min(point.z for point in points) - .002
    for obj in list(scene.objects):
        if obj.name.startswith('PREVIEW_light'):
            bpy.data.objects.remove(obj, do_unlink=True)
    vertical = Vector((0, 0, 1))
    # Broad sources keep open framework readable and catch satin bevels.
    previews.area('PREVIEW_light_key', target + direction * 3 - right * 2 + vertical * 3,
                  target, 330, 3.3, (1, .94, .87))
    previews.area('PREVIEW_light_fill', target + direction * 2.7 + right * 2.2 + vertical * .8,
                  target, 150, 2.8, (.82, .91, 1))
    previews.area('PREVIEW_light_rim', target - direction * 2.1 + right * 1.4 + vertical * 2.6,
                  target, 310, 2.55, (.86, .94, 1))


def write_image(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print('PREVIEW_WRITTEN', path, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('view', choices=(*VIEWS, *DRAFT_VIEWS, 'all', 'compare'), default='all', nargs='?')
    parser.add_argument('--draft', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    draft_dir = ROOT / 'studies_t3a'
    if args.view == 'compare':
        if bpy.data.filepath or bpy.data.objects.get('EFT_Bind'):
            parser.error('Comparison requires Blender startup without an input blend')
        models, labels = load_tiers()
        camera = setup(args.draft, True)
        for model in models:
            model.hide_render = False
            if model.name.split('.')[0] in CLOTHING and model.name not in CLOTHING:
                original = bpy.data.objects[model.name.split('.')[0]]
                if len(model.data.polygons) == len(original.data.polygons):
                    model.data.materials.clear()
                    for material in original.data.materials:
                        model.data.materials.append(material)
                    for poly, original_poly in zip(model.data.polygons, original.data.polygons):
                        poly.material_index = original_poly.material_index
                        poly.use_smooth = True
        studio(camera, add_floor(0), evaluated_points(models), COMPARISON_VIEW, labels)
        write_image((draft_dir if args.draft else ROOT) / 'previews_tiers_v2.png')
        return

    if not args.draft and Path(bpy.data.filepath).name != 'exo_t3a.blend':
        parser.error('Final previews require exo_t3a.blend')
    if args.view in DRAFT_VIEWS and not args.draft:
        parser.error('Pose inspection views require --draft')

    import review

    camera = setup(args.draft, False)
    floor = add_floor(0)
    destination = draft_dir if args.draft else ROOT / 'previews_t3a'
    for name in VIEWS if args.view == 'all' else (args.view,):
        pose, direction, solo = (VIEWS | DRAFT_VIEWS)[name]
        review.set_pose(pose)
        for ref in CLOTHING:
            bpy.data.objects[ref].hide_render = solo
        models = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH'
                  and not obj.hide_render and obj != floor]
        studio(camera, floor, evaluated_points(models), direction)
        write_image(destination / (name + '.png'))


if __name__ == '__main__':
    main()

