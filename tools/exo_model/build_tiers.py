"""Build a tier from base_scene.blend with Blender 5.3 in background mode.

blender -b base_scene.blend --python-exit-code 1 --python build_tiers.py -- 2
Use 3 for the advanced frame. See tier_previews.py and tier_qa.py for review.
"""
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from geometry import Geometry
import previews
import review


class DistanceGeometry(Geometry):
    """Keep the major silhouettes, with four- to six-sided cables and shafts."""

    def tube(self, points, r, style=0, n=6, end_radius=None, bones=None):
        if r <= .0045 and len(points) == 2 and (Vector(points[0])-Vector(points[1])).length < .023:
            return
        count = 4 if r < .011 else 5 if r < .025 else 6
        super().tube(points, r, style, min(n,count), end_radius, bones)


def setup_studio(tier):
    camera = previews.setup()
    previews.render('three_quarter', camera, save_png=False)
    studio = bpy.data.collections.new('Preview Studio')
    bpy.context.scene.collection.children.link(studio)
    for obj in list(bpy.context.scene.objects):
        if obj.name.startswith('PREVIEW_'):
            for collection in list(obj.users_collection):
                collection.objects.unlink(obj)
            studio.objects.link(obj)
    bpy.context.view_layer.layer_collection.children[studio.name].hide_viewport = True
    bpy.context.scene.render.filepath = f'//previews_t{tier}/three_quarter.png'
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.overlay.show_overlays = False
                space.region_3d.view_distance = 2.8
                space.region_3d.view_location = (0, 0, .82)
                space.region_3d.view_rotation = Vector((1.3, -2.1, .30)).to_track_quat('Z', 'Y')
                space.region_3d.view_perspective = 'ORTHO'
                space.shading.color_type = 'TEXTURE'
                space.shading.type = 'MATERIAL'


def build(tier):
    import tier_arms
    import tier_legs
    import tier_gearboxes
    import tier_torso
    import tier_atlas
    from clearance import fit

    if tier not in (2, 3) or Path(bpy.data.filepath).resolve() != ROOT / 'base_scene.blend':
        raise ValueError('Open base_scene.blend and specify tier 2 or 3.')
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.preferences.filepaths.file_preview_type = 'NONE'
    rig = bpy.data.objects['EFT_Bind']
    for obj in bpy.context.scene.objects:
        is_ref = obj.name in ('REF_pants', 'REF_top')
        obj.hide_render = not is_ref
        obj.hide_set(not is_ref)
        if is_ref:
            obj.hide_viewport = False

    finishes = [bpy.data.materials.new(f'ConstructionFinish{i}') for i in range(8)]
    lods = []
    for level in (0, 1):
        review.set_pose('rest')
        builder = DistanceGeometry if level == 1 else Geometry
        geometry = builder(level, rig, finishes)
        tier_torso.build(geometry, tier)
        tier_legs.build(geometry, tier)
        tier_arms.build(geometry, tier)
        tier_gearboxes.build(geometry, tier)
        objects = geometry.finish()
        total = 0
        for obj in objects:
            obj.data.calc_loop_triangles()
            total += len(obj.data.loop_triangles)
        limit = {2: (18000, 6500), 3: (22000, 8000)}[tier][level]
        print(f'T{tier} LOD{level}: {total}/{limit} triangles', flush=True)
        if total > limit:
            raise RuntimeError(f'Tier {tier} LOD{level} exceeds its triangle budget.')
        lods.append(objects)

    bpy.context.view_layer.update()
    # The garment-following suspension uses the same multi-pose fit as Tier 1.
    # Machined parts and cuff rims retain their authored sections.
    suspension = {'harness', 'belt', 'lumbar', 'back', 'hipBridgeL', 'hipBridgeR',
                  'shoulderSupportL', 'shoulderSupportR', 'footL', 'footR',
                  'kneeL', 'kneeR', 'shinL', 'shinR', 'thighL', 'thighR',
                  'kneeDriveL', 'thighStrapL', 'thighStrapR', 'calfStrapL', 'calfStrapR'}
    fit([o for lod in lods for o in lod if o.name.split('_', 1)[1] in suspension])
    review.set_pose('rest')
    tier_atlas.apply_atlas(*lods, tier)
    for material in finishes:
        if not material.users:
            bpy.data.materials.remove(material)
    setup_studio(tier)
    review.restore_pose()
    rig.data.pose_position = 'REST'
    detail = bpy.data.collections['EXO_LOD1']
    detail.hide_render = True
    bpy.context.view_layer.layer_collection.children[detail.name].hide_viewport = True
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = lods[0][0]
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / f'exo_t{tier}.blend'), compress=True)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if len(args) != 1:
        raise ValueError('Pass -- 2 or -- 3.')
    build(int(args[0]))
