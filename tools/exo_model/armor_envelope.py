"""Set the formed skins against the clothed deformation envelope before extrusion."""
import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import closest_point_on_tri
from mathutils.bvhtree import BVHTree
import review


class Envelope:
    def __init__(self):
        rig = review.ARM
        world = rig.matrix_world.copy()
        inv_world = world.inverted()
        self.poses = []
        self.triangles_by_tree={}
        try:
            for pose in review.POSES:
                review.set_pose(pose)
                dg = bpy.context.evaluated_depsgraph_get()
                meshes = [review._mesh(bpy.data.objects[n], dg) for n in ('REF_top', 'REF_pants')]
                vertices, triangles = [], []
                for points, faces in meshes:
                    start = len(vertices)
                    vertices += points
                    triangles.extend(tuple(start + i for i in face) for face in faces)
                tree = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
                self.triangles_by_tree[id(tree)]=[tuple(vertices[k] for k in tri) for tri in triangles]
                bones = {p.name: world @ p.matrix @ p.bone.matrix_local.inverted() @ inv_world
                         for p in rig.pose.bones}
                self.poses.append((tree, bones))
        finally:
            review.restore_pose()

    def fit(self, sheet, bone, thickness):
        # Seek the shortest inward translation of each forming station that
        # fits the outer face in all poses while retaining room behind the sheet.
        # The compiled mesh remains one rigid part with a single bone influence.
        result = []
        for row, normals in zip(sheet.points, sheet.normals):
            out = []
            for point, normal in zip(row, normals):
                rays = []
                for tree, bones in self.poses:
                    transform = bones[bone]
                    p = transform @ point
                    n = (transform.to_3x3() @ normal).normalized()
                    rays.append((tree,p,n))
                def score(offset):
                    inner,outer=1,0
                    for tree,p,n in rays:
                        a = p + n*(offset-thickness)
                        b = p + n*offset
                        close, direction, _, d = tree.find_nearest(a)
                        if (a-close).dot(direction) < -.001:
                            d = -d
                        inner=min(inner,d)
                        outer=max(outer,tree.find_nearest(b)[3])
                    # Inner fit is prioritized in the small overlap of a posed sleeve
                    # with the reference torso and at the hip crease.
                    return 8*max(0,.0080-inner) + max(0,outer-.0275) + .08*abs(offset)
                baseline=score(0)
                if baseline > .00025:
                    options=range(-17,6)
                    best=min(options,key=lambda i:score(i*.001))
                else:
                    best=0
                delta=normal*(best*.001)
                # At an articulated crease the direction toward the cloth in a
                # crouch differs from the rest normal. Allow a small tangential
                # movement of the forming station to follow both envelopes.
                for iteration in range(45):
                    before=delta.copy()
                    for tree,bones in self.poses:
                        mat=bones[bone]
                        rot=mat.to_3x3()
                        for depth,goal,minimum in ((0,.0273,False),(-thickness,.0082,True)):
                            sample=mat @ (point+delta+normal*depth)
                            close,face_normal,_,d=tree.find_nearest(sample)
                            direction=sample-close
                            if direction.dot(face_normal)<0:
                                d=-d
                                direction=-direction
                            diff=goal-d
                            if (diff>0)==minimum and direction.length>.00001:
                                delta+=rot.transposed() @ direction.normalized()*diff*.64
                    if delta.length>.020:
                        delta.normalize()
                        delta*=.020
                    if (delta-before).length<.00004:
                        break
                out.append(delta)
            result.append(out)
        def smoothed(j,i):
            here=result[j][i]
            neighbors=[result[y][x] for y,x in ((j-1,i),(j+1,i),(j,i-1),(j,i+1))
                       if 0<=y<sheet.h and 0<=x<sheet.w]
            return here*.90 + .10*sum(neighbors,Vector())/len(neighbors)
        return [[p+smoothed(j,i) for i,p in enumerate(row)]
                for j,row in enumerate(sheet.points)]

    def mounting_clearance(self, bone, point):
        for tree,bones in self.poses:
            sample=bones[bone] @ point
            hit,n,_,d=tree.find_nearest(sample)
            if not .0085<d<.0265 or (sample-hit).dot(n)<0:
                return False
        return True

    def finish_surface(self,obj,limit=.02915,max_move=.0075):
        """Check bevels, bolts and interpolated points between forming stations."""
        mesh=obj.data
        mesh.calc_loop_triangles()
        pts=np.asarray([v.co[:] for v in mesh.vertices])
        source=pts.copy()
        tris=[tuple(t.vertices) for t in mesh.loop_triangles]
        edges=sorted({tuple(sorted((a,b))) for tri in tris for a,b in zip(tri,tri[1:]+tri[:1])})
        supports=[(i,) for i in range(len(pts))]+edges+tris
        poses=[]
        for tree,bones in self.poses:
            mat=bones[obj.vertex_groups[0].name]
            inv=mat.to_3x3().transposed()
            candidates=[]
            for ids in supports:
                p=mat @ Vector(pts[list(ids)].mean(axis=0))
                if tree.find_nearest(p)[3]>.027:
                    candidates.append((ids,list(ids)))
            if candidates:
                poses.append((tree,mat,inv,candidates))
        for _ in range(12):
            change=np.zeros_like(pts)
            needed=np.zeros(len(pts))
            for tree,mat,inv,candidates in poses:
                for ids,idx in candidates:
                    p=mat @ Vector(pts[idx].mean(axis=0))
                    hit,_,_,d=tree.find_nearest(p)
                    excess=d-limit
                    if excess<.00004:
                        continue
                    vec=np.asarray(inv @ ((hit-p)*(excess/d)))
                    for i in ids:
                        if excess>needed[i]:
                            change[i]=vec
                            needed[i]=excess
            if max(needed)<.00006:
                break
            pts+=change*.86
            delta=pts-source
            pts=source+delta/np.maximum(1,np.linalg.norm(delta,axis=1)/max_move)[:,None]
        mesh.vertices.foreach_set('co',pts.astype(np.float32).ravel())
        mesh.update()

    def finish_facets(self,obj):
        """Locate high spots inside a facet that vertex or centroid checks miss."""
        mesh=obj.data
        mesh.calc_loop_triangles()
        pts=[v.co.copy() for v in mesh.vertices]
        bone=obj.vertex_groups[0].name
        faces=[tuple(t.vertices) for t in mesh.loop_triangles]
        corners=(Vector((1,0,0)),Vector((0,1,0)),Vector((0,0,1)))
        for iteration in range(8):
            corrections={}
            for tree,bones in self.poses:
                mat=bones[bone]
                inv=mat.to_3x3().transposed()
                world=[mat @ p for p in pts]
                cloth=self.triangles_by_tree[id(tree)]
                def inspect(tri,points,weights,level):
                    a,b,c=points
                    center=(a+b+c)/3
                    near,_,face,d=tree.find_nearest(center)
                    if d>.02960:
                        w=sum(weights,Vector())/3
                        delta=inv @ ((near-center)*((d-.02935)/d))
                        denom=w.length_squared
                        for idx,f in zip(tri,w):
                            step=delta*(f/denom)
                            if idx not in corrections or step.length_squared>corrections[idx].length_squared:
                                corrections[idx]=step
                        return
                    if all((p-closest_point_on_tri(p,*cloth[face])).length<=.02975 for p in points):
                        return
                    if level==7 or max((p-center).length for p in points)+d<.02975:
                        return
                    ab,bc,ca=(a+b)/2,(b+c)/2,(c+a)/2
                    x,y,z=weights
                    xy,yz,zx=(x+y)/2,(y+z)/2,(z+x)/2
                    for pp,ww in (((a,ab,ca),(x,xy,zx)),((ab,b,bc),(xy,y,yz)),
                                  ((ca,bc,c),(zx,yz,z)),((ab,bc,ca),(xy,yz,zx))):
                        inspect(tri,pp,ww,level+1)
                for tri in faces:
                    inspect(tri,[world[k] for k in tri],corners,0)
            if not corrections:
                break
            for i,delta in corrections.items():
                pts[i]+=delta*min(.76,.0014/max(.00001,delta.length))
        mesh.vertices.foreach_set('co',np.asarray(pts,dtype=np.float32).ravel())
        mesh.update()
