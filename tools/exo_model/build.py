"""Build from the supplied base_scene.blend in headless Blender. See REPORT.md."""
import sys
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from geometry import Geometry
import arms
import legs
import torso
import atlas


def build():
    if Path(bpy.data.filepath).resolve() != ROOT / 'base_scene.blend':
        raise RuntimeError('Open the supplied base_scene.blend as the build input')
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.preferences.filepaths.file_preview_type = 'NONE'
    rig = bpy.data.objects['EFT_Bind']
    for obj in bpy.context.scene.objects:
        is_ref = obj.name in ('REF_pants','REF_top')
        obj.hide_render = not is_ref
        obj.hide_set(not is_ref)
        if is_ref:
            obj.hide_viewport = False
    mats = [bpy.data.materials.new('ConstructionFinish' + str(i)) for i in range(8)]
    lods = []
    for level in (0,1):
        g = Geometry(level, rig, mats)
        torso.build(g)
        legs.build(g)
        arms.build(g)
        objects = g.finish()
        lods.append(objects)
        for obj in objects:
            obj.data.calc_loop_triangles()
        print('LOD',level,'triangles',sum(len(o.data.loop_triangles) for o in objects),flush=True)
    bpy.context.view_layer.update()
    from clearance import fit
    fit(lods[0]+lods[1])
    if '--draft' in sys.argv:
        colors = ((.22,.26,.26),(.04,.056,.052),(.18,.22,.10),(.48,.54,.55),(.32,.25,.13),(.085,.08,.055),(.88,.44,.06),(.28,.31,.3))
        for mat,color in zip(mats,colors):
            mat.diffuse_color=(*color,1)
        filename = 'fit_draft.blend'
    else:
        atlas.apply_atlas(*lods)
        for mat in mats:
            if not mat.users:
                bpy.data.materials.remove(mat)
        filename = 'exo_model.blend'
    import previews
    if '--draft' not in sys.argv:
        # Leave a working F12 product shot in a separate, optional studio collection.
        camera=previews.setup()
        previews.render('three_quarter',camera,save_png=False)
        studio=bpy.data.collections.new('Preview Studio')
        bpy.context.scene.collection.children.link(studio)
        for obj in list(bpy.context.scene.objects):
            if obj.name.startswith('PREVIEW_'):
                for old in list(obj.users_collection):
                    old.objects.unlink(obj)
                studio.objects.link(obj)
        bpy.context.view_layer.layer_collection.children[studio.name].hide_viewport=True
        bpy.context.scene.render.filepath='//previews/three_quarter.png'
    else:
        previews.install_reference_materials()
    for obj in lods[1]:
        obj.hide_render=False
    bpy.context.view_layer.layer_collection.children['EXO_LOD1'].hide_viewport=True
    bpy.data.collections['EXO_LOD1'].hide_render=True
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = lods[0][0]
    rig.data.pose_position = 'REST'
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.overlay.show_overlays = False
                space.region_3d.view_distance = 2.85
                space.region_3d.view_location = (0,0,.80)
                space.region_3d.view_rotation = Vector((1.5,-2.5,.50)).to_track_quat('Z','Y')
                space.region_3d.view_perspective = 'ORTHO'
                space.shading.color_type = 'TEXTURE'
                space.shading.type = 'MATERIAL'
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / filename),compress=True)


if __name__ == '__main__':
    build()

