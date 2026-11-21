import sys
from pathlib import Path
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
import bpy
import armor_axial, armor_previews, build_t3a, review
ctx=build_t3a.Context()
armor_axial.build(ctx)
ctx.suspension()
for k, rgb in enumerate(((.31,.34,.37),(.030,.034,.041),(.38,.41,.43),(.15,.16,.17),(.31,.35,.36),(.063,.069,.075))):
 m=bpy.data.materials.new('Axial draft %s'%k)
 m.use_nodes=True
 s=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
 s.inputs['Base Color'].default_value=(*rgb,1)
 s.inputs['Metallic'].default_value=.47 if k%2==0 else .2
 s.inputs['Roughness'].default_value=.39
 for obj in ctx.objects:
  if obj.name.startswith('EXO_'):
   obj.data.materials.append(m)
for obj in ctx.objects:
 if obj.name.startswith('EXO_'):
  for p in obj.data.polygons:
   p.material_index=1+obj.data.attributes['armor_finish'].data[p.index].value
camera=armor_previews.setup(True,False)
floor=armor_previews.add_floor(0)
s=bpy.context.scene
s.cycles.samples=5
s.render.resolution_percentage=45
s.render.threads_mode='FIXED'
s.render.threads=6
for name in ('front','three_quarter'):
 pose,direction,solo=armor_previews.VIEWS[name]
 review.set_pose(pose)
 for ref in armor_previews.CLOTHING:
  bpy.data.objects[ref].hide_render=False
 models=[obj for obj in s.objects if obj.type=='MESH' and not obj.hide_render and obj!=floor]
 armor_previews.studio(camera,floor,armor_previews.evaluated_points(models),direction)
 armor_previews.write_image(root/('axial_'+name+'.png'))



