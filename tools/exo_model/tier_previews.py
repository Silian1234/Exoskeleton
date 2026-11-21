"""Render tier views and a same-scale comparison without changing source blends.

blender -b exo_t2.blend --python tier_previews.py -- t2 all
blender -b exo_t3.blend --python tier_previews.py -- t3 front
blender -b --python tier_previews.py -- compare
"""
import os
import sys
import bpy

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def render_tier(tier, requested):
    import previews
    if requested != 'all' and requested not in previews.VIEWS:
        raise ValueError('Unknown view: ' + requested)
    destination = os.path.join(ROOT, 'previews_' + tier)
    os.makedirs(destination, exist_ok=True)
    camera = previews.setup()
    for name in previews.VIEWS if requested == 'all' else [requested]:
        previews.render(name, camera, save_png=False)
        bpy.context.scene.render.filepath = os.path.join(destination, name + '.png')
        bpy.ops.render.render(write_still=True)
        print('PREVIEW_WRITTEN', bpy.context.scene.render.filepath, flush=True)


def compare(test=False):
    from mathutils import Vector
    bpy.ops.wm.read_factory_settings(use_empty=True)
    direction = Vector((1.4, -1.05, .18)).normalized()
    right = (-direction).to_track_quat('-Z', 'Y').to_matrix().col[0]
    right.z = 0
    right.normalize()
    for tier, file, x in [('t1', 'exo_model.blend', -1.35),
                          ('t2', 'exo_t2.blend', 0.0),
                          ('t3', 'exo_t3.blend', 1.35)]:
        path = os.path.join(ROOT, 'exo_model.blend' if test else file)
        with bpy.data.libraries.load(path, link=False) as (source, target):
            target.objects = [name for name in source.objects if name == 'EFT_Bind'
                              or name in ('REF_top', 'REF_pants') or name.startswith('EXO_')]
        for obj in target.objects:
            if obj is None:
                continue
            bpy.context.scene.collection.objects.link(obj)
            if obj.parent is None:
                obj.location += right * x
            if obj.type == 'MESH' and obj.name.startswith('EXO_'):
                for slot in obj.material_slots:
                    if slot.material and slot.material.use_nodes:
                        for node in slot.material.node_tree.nodes:
                            if node.type == 'TEX_IMAGE' and node.image:
                                basename = os.path.basename(bpy.path.abspath(node.image.filepath))
                                folder = 'textures' if tier == 't1' or test else 'textures_' + tier
                                candidate = os.path.join(ROOT, folder, basename)
                                if os.path.isfile(candidate):
                                    node.image.filepath = candidate
    import previews
    previews.VIEWS['three_quarter'] = ('rest', (1.4, -1.05, .18), False)
    camera = previews.setup()
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and (obj.name.startswith('REF_top') or obj.name.startswith('REF_pants')):
            obj.hide_render = False
    scene = bpy.context.scene
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 950
    previews.render('three_quarter', camera, save_png=False)
    camera.data.ortho_scale *= 1.12 * (scene.render.resolution_x / scene.render.resolution_y)
    camera.location.z -= .08
    for label, offset in [('T1', -1.35), ('T2', 0), ('T3', 1.35)]:
        curve = bpy.data.curves.new('PREVIEW_label_' + label, 'FONT')
        curve.body = label
        curve.align_x = 'CENTER'
        curve.size = .12
        obj = bpy.data.objects.new('PREVIEW_label_' + label, curve)
        scene.collection.objects.link(obj)
        obj.location = right * offset + Vector((0, 0, 1.95)) + direction * .5
        obj.rotation_euler = camera.rotation_euler
    scene.render.filepath = os.path.join(ROOT, 'previews_tiers_test.png' if test else 'previews_tiers.png')
    bpy.ops.render.render(write_still=True)
    print('PREVIEW_WRITTEN', scene.render.filepath, flush=True)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if args and args[0] in ('compare', 'compare_test'):
        compare(test=args[0] == 'compare_test')
    elif args and args[0] in ('t2', 't3'):
        render_tier(args[0], args[1] if len(args) > 1 else 'all')
    else:
        raise ValueError('Use: t2|t3 [all|view], or compare')



