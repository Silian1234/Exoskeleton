"""Planar rigid C-braces fitted to the evaluated garment in every pose."""
import math, itertools
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import bpy
import review

_POSED = {}
_RAYS = {}
_FIT = {}

def prepare():
    _POSED.clear()
    _RAYS.clear()
    obj=bpy.data.objects['REF_pants']
    for pose in review.POSES:
        review.set_pose(pose)
        dep=bpy.context.evaluated_depsgraph_get()
        verts,tris=review._mesh(bpy.data.objects['REF_pants'],dep)
        for side in ('L','R'):
            for bone in ('Thigh1','Calf'):
                name='Base Human'+side+bone
                arm=review.ARM
                mat=arm.matrix_world @ arm.pose.bones[name].matrix @ arm.data.bones[name].matrix_local.inverted() @ arm.matrix_world.inverted()
                inv=mat.inverted()
                local=[inv @ v for v in verts]
                _POSED[(side,bone,pose)]=BVHTree.FromPolygons(local,tris,all_triangles=True)
                valid=set()
                for group in obj.vertex_groups:
                    if group.name in ('Base Human'+side+bone, 'Base Human'+side+'Thigh2' if bone=='Thigh1' else ''):
                        valid.add(group.index)
                selected=[sum(w.weight for w in v.groups if w.group in valid) > .35 for v in obj.data.vertices]
                subset=[tri for tri in tris if sum(selected[i] for i in tri)>=2]
                _RAYS[(side,bone,pose)]=BVHTree.FromPolygons(local,subset,all_triangles=True)
    review.set_pose('rest')

def _shape(c,sign,rx,ry,width,n):
    # A 200-degree C-brace, open at the inner rear.
    angles=[math.radians(-150+200*i/n) for i in range(n+1)]
    vs=[]
    for dz,extra in ((-width/2,0),(width/2,0),(-width/2,.005),(width/2,.005)):
        for a in angles:
            vs.append(c+Vector((sign*(rx+extra)*math.cos(a),(ry+extra)*math.sin(a),dz)))
    k=n+1; fs=[]
    for i in range(n):
        j=i+1
        fs.extend(((i,j,k+j,k+i),(2*k+j,2*k+i,3*k+i,3*k+j),
                   (i,2*k+i,2*k+j,j),(k+j,3*k+j,3*k+i,k+i)))
    fs.extend(((0,k,3*k,2*k),(n,2*k+n,3*k+n,k+n)))
    return vs,fs

def _fit(side,thigh):
    key=(side,thigh)
    if key in _FIT: return _FIT[key]
    sign=1 if side=='L' else -1
    bone='Thigh1' if thigh else 'Calf'
    width=.040 if thigh else .035
    trees=[_POSED[(side,bone,p)] for p in review.POSES]
    raytrees=[_RAYS[(side,bone,p)] for p in review.POSES]
    # Test actual planar bands against complete garment geometry, including
    # the opposite leg. Search the height and ellipse axes as a whole.
    zs=(.68,) if thigh else (.16,.20,.24,.28,.32,.36,.40)
    radii=(.075,.085,.095,.105,.115,.125,.135,.145,.155,.165,.175,.185,.195,.205,.215,.225)
    best=None
    for z,dx,dy in itertools.product(zs,(-.01,0,.01),(-.015,0,.015)):
        cx=.178-.125*(z-.3)+dx; cy=(-.024 if thigh else .039)+dy
        c=Vector((sign*cx,cy,z))
        for rx in radii:
            for ry in radii:
                score=rx*ry
                if best and score >= best[0]: continue
                # Reject bands inside the clothing even where surfaces do not
                # cross. Rays begin outside the selected leg, then travel inward.
                outside=True
                for tree in raytrees:
                    for j in range(13):
                        a=math.radians(-150+200*j/12)
                        ray=Vector((sign*math.cos(a),math.sin(a),0))
                        reach=min(.22,(cx-.006)/max(.001,-math.cos(a)))
                        limit=1/math.sqrt((math.cos(a)/rx)**2+(math.sin(a)/ry)**2)
                        for dz in (-width/2,0,width/2):
                            origin=c+Vector((0,0,dz))
                            hit=tree.ray_cast(origin+ray*reach,-ray,reach)[0]
                            if hit is not None and (hit-origin).dot(ray)>limit-.007:
                                outside=False; break
                        if not outside: break
                    if not outside: break
                if not outside: continue
                # The low-poly LOD is the stricter, inscribed approximation.
                vs,fs=_shape(c,sign,rx,ry,width,12)
                triangles=[]
                for f in fs:
                    triangles.extend(((f[0],f[1],f[2]),(f[0],f[2],f[3])))
                cuff=BVHTree.FromPolygons(vs,triangles,all_triangles=True)
                if any(cuff.overlap(t) for t in trees): continue
                # Check the inner rim at vertices and edge midpoints; leave
                # clearance for the higher-resolution LOD and interpolation.
                samples=vs[:26]+[(vs[i]+vs[i+1])*.5 for i in list(range(12))+list(range(13,25))]
                if any(t.find_nearest(v,.0055)[0] is not None for t in trees for v in samples): continue
                best=(score,c,rx,ry,width)
    if best is None: raise RuntimeError('No collision-free cuff found for '+side+' '+bone)
    _,c,rx,ry,width=best
    _FIT[key]=(c,rx,ry,width)
    print('CUFF FIT',side,bone,round(c.z,3),round(rx,3),round(ry,3),flush=True)
    return _FIT[key]

def leg_webbing(g,cloth,sign,thigh,side):
    c,rx,ry,width=_fit(side,thigh)
    # Both LODs share the same fitted elliptical profile.
    n=24 if g.lod==0 else 12
    vs,fs=_shape(c,sign,rx,ry,width,n)
    bone='Base Human'+side+('Thigh1' if thigh else 'Calf')
    g.part(('thighCuff' if thigh else 'calfCuff')+side,bone)
    g.mesh(vs,fs,1)
    anchor=c+Vector((sign*(rx+.005),0,0))
    g.box(anchor+Vector((sign*.004,0,0)),(.012,.027,.022),2,bevel=.002)
    a=anchor+Vector((sign*.012,-.012,0)); b=anchor+Vector((sign*.012,.024,0))
    g.beam(a,b,.008,.006,0,bevel=.001,ref=(1,0,0))
    for dy in (-.009,.009):
        g.rod(anchor+Vector((sign*.011,dy,0)),anchor+Vector((sign*.016,dy,0)),.0035,7,n=6)
    return anchor








