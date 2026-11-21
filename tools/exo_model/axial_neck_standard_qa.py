from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).parent))
import bpy, armor_axial, build_t3a, review
from mathutils import Vector
from mathutils.bvhtree import BVHTree
c=build_t3a.Context()
armor_axial.build(c)
c.suspension()
for lod in (0,1):
    col=bpy.data.collections['EXO_LOD'+str(lod)]
    col.hide_viewport=False
    bpy.context.view_layer.layer_collection.children[col.name].hide_viewport=False
for angle in review.POSES:
    review.set_pose(angle)
    dg=bpy.context.evaluated_depsgraph_get()
    top=BVHTree.FromPolygons(*review._mesh(bpy.data.objects['REF_top'],dg),all_triangles=True)
    hitcount=0; neargap=1
    for ob in c.objects:
        if 'armorGorget' not in ob.name and 'gorgetBacking' not in ob.name: continue
        vv,tt=review._mesh(ob,dg)
        guard=BVHTree.FromPolygons(vv,tt,all_triangles=True)
        hits=len(guard.overlap(top))
        if hits:
            ids={i for a,b in guard.overlap(top) for i in tt[a]}
            print('CROSS',angle,ob.name,hits,[(round(min(vv[i][k] for i in ids),3),round(max(vv[i][k] for i in ids),3)) for k in range(3)])
        hitcount+=hits
        gap=min(top.find_nearest(v)[3] for v in vv)
        if angle==0: print(ob.name,round(gap*1000,2))
        neargap=min(neargap,gap)
    print(angle,hitcount,round(neargap*1000,2))




