"""Small bind-space clearance corrections for the supplied posed clothing.

The constraints use evaluated garments. Source bones and weights are read-only.
Each pass moves the vertices supporting the tightest nearby samples, converting
the direction back to bind coordinates through their skinning transforms.
"""

import bpy
import numpy as np


import review

from proximity import Garment, Pair

TARGET=.0065


def _pose_cache(objects):
    data=[]
    for pose in review.POSES:
        review.set_pose(pose)
        deps=bpy.context.evaluated_depsgraph_get()
        verts=[]; triangles=[]
        for name in ('REF_pants','REF_top'):
            pts,tris=review._mesh(bpy.data.objects[name],deps)
            triangles.extend(tuple(i+len(verts) for i in t) for t in tris)
            verts.extend(pts)
        tree=Garment(verts,triangles)
        arm=review.ARM
        bones={b.name:np.asarray(b.matrix @ b.bone.matrix_local.inverted())[:3,:] for b in arm.pose.bones}
        mats={}
        for o in objects:
            transforms=[]
            for vertex in o.data.vertices:
                transforms.append(sum(bones[o.vertex_groups[w.group].name]*w.weight for w in vertex.groups))
            mats[o.name]=np.asarray(transforms)
        data.append((pose,tree,mats))
    review.restore_pose()
    return data


def fit(objects):
    cache=_pose_cache(objects)
    for obj in objects:
        verts=np.asarray([v.co[:] for v in obj.data.vertices],dtype=float)
        original=verts.copy()
        obj.data.calc_loop_triangles()
        triangles=[tuple(t.vertices) for t in obj.data.loop_triangles]
        neighborhoods=[]
        for pose,tree,all_mats in cache:
            mat=all_mats[obj.name]
            positions=np.einsum('nij,nj->ni',mat[:,:,:3],verts)+mat[:,:,3]
            neighborhoods.append((Pair(tree,positions,triangles,.020),mat,np.linalg.inv(mat[:,:,:3])))
        for iteration in range(30):
            largest=np.zeros(len(verts))
            updates=np.zeros_like(verts)
            for pair,mat,inv in neighborhoods:
                pos=np.einsum('nij,nj->ni',mat[:,:,:3],verts)+mat[:,:,3]
                for indices,delta,d in pair.features(pos,TARGET):
                    if d<1e-9:continue
                    direction=delta/d
                    for i in indices:
                        need=TARGET-d
                        if need>largest[i]:
                            largest[i]=need
                            updates[i]=(inv[i] @ direction)*need
            if largest.max()<.00006:
                break
            verts+=updates*.72
            # Keep every manufactured edge within a small local adjustment.
            diff=verts-original
            scale=np.maximum(1.,np.linalg.norm(diff,axis=1)/.012)
            verts=original+diff/scale[:,None]
        obj.data.vertices.foreach_set('co',verts.astype(np.float32).ravel())
        obj.data.update()
    bpy.context.view_layer.update()


