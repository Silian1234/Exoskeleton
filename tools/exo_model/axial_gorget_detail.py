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
objects=[o for o in c.objects if 'armorGorget' in o.name or 'gorgetBacking' in o.name]
if '--' in sys.argv:
 import clearance
 clearance.TARGET=.0061
 plates=[o for o in objects if o.get('t3a_armor')]
 for obj in plates: c.envelope.finish_surface(obj)
 clearance.fit(plates)
for lod in (0,1):
    col=bpy.data.collections['EXO_LOD'+str(lod)]
    col.hide_viewport=False
    bpy.context.view_layer.layer_collection.children[col.name].hide_viewport=False
for pose, angle in [(p,0) for p in review.POSES]+[('rest',int(a)) for a in range(-75,76,3)]:
    review.set_pose(pose)
    review._rotate('Base HumanNeck',Vector((0,0,1)),angle)
    dg=bpy.context.evaluated_depsgraph_get()
    top=BVHTree.FromPolygons(*review._mesh(bpy.data.objects['REF_top'],dg),all_triangles=True)
    hitcount=0
    for ob in objects:
        vv,tt=review._mesh(ob,dg)
        guard=BVHTree.FromPolygons(vv,tt,all_triangles=True)
        hits=len(guard.overlap(top))
        if hits: print('CROSS',pose,angle,ob.name,hits)
        hitcount+=hits
        if angle==0:
            edges={(min(i,j),max(i,j)) for a,b,c in tt for i,j in ((a,b),(b,c),(c,a))}
            samples=vv+[(vv[a]+vv[b])/2 for a,b in edges]+[(vv[a]+vv[b]+vv[c])/3 for a,b,c in tt]
            gaps=[top.find_nearest(v)[3] for v in samples]
            max_idx=max(range(len(gaps)),key=gaps.__getitem__)
            if True:
                print('GAP',pose,ob.name,round(min(gaps)*1000,2),round(gaps[max_idx]*1000,2),tuple(round(x,4) for x in samples[max_idx]))
    if hitcount: print(pose,angle,hitcount)

