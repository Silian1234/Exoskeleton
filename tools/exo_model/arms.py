"""EXO-3 arm assists. World-space construction; caller supplies shared geometry builder."""
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from math import cos, sin, pi
import numpy as np

def sleeve_bvh():
    """Build in world space from the evaluated reference clothing in bind pose."""
    obj = bpy.data.objects['REF_top'].evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = obj.to_mesh()
    verts = [obj.matrix_world @ v.co for v in mesh.vertices]
    faces = [tuple(poly.vertices) for poly in mesh.polygons]
    tree = BVHTree.FromPolygons(verts, faces)
    obj.to_mesh_clear()
    return tree

def band(g, tree, center, axis, fallback, width, thickness, style, sides, side_sign):
    c=Vector(center); d=Vector(axis).normalized()
    u=Vector((0,0,1)); u=(u-d*u.dot(d)).normalized(); v=d.cross(u).normalized()
    dirs=[u*cos(2*pi*i/sides)+v*sin(2*pi*i/sides) for i in range(sides)]
    # Sample each edge and the middle. Use the greater adjacent samples to keep
    # straight polygon chords outside the irregular fabric surface.
    radii=[]; misses=0
    for z in (-width/2, 0, width/2):
        row=[]
        for ray in dirs:
            hit, normal, index, dist = tree.ray_cast(c+d*z, ray, .18)
            if hit is None:
                misses+=1
                dist=fallback
            row.append(dist)
        radii.append(row)
    print('ARM_CUFF', tuple(round(x,4) for x in c), 'misses', misses,
          'surface_range', round(min(min(row) for row in radii),4), round(max(max(row) for row in radii),4))
    verts=[]
    for layer,z in enumerate((-width/2,width/2,-width/2,width/2)):
        sample=0 if layer%2==0 else 2
        for i,ray in enumerate(dirs):
            r=max(radii[j][k%sides] for j in (sample,1) for k in (i-1,i,i+1))
            r += .020 if layer<2 else .015
            verts.append(tuple(c+d*z+r*ray))
    faces=[]
    active=[i for i in range(sides) if (dirs[i].x*side_sign > .3 and dirs[(i+1)%sides].x*side_sign > .3 and (axis.length>.28 or min(dirs[i].z,dirs[(i+1)%sides].z)>-.74))]
    for i in active:
        j=(i+1)%sides
        faces.extend([(i,j,sides+j,sides+i),(2*sides+j,2*sides+i,3*sides+i,3*sides+j),
                      (j,i,2*sides+i,2*sides+j),(sides+i,sides+j,3*sides+j,3*sides+i)])
    # Cap both open ends of the contoured partial cuff.
    for i in active:
        if (i-1)%sides not in active:
            faces.append((i,sides+i,3*sides+i,2*sides+i))
        if (i+1)%sides not in active:
            j=(i+1)%sides
            faces.append((j,2*sides+j,3*sides+j,sides+j))
    used=sorted({index for face in faces for index in face})
    remap={old:new for new,old in enumerate(used)}
    g.mesh([verts[i] for i in used], [tuple(remap[i] for i in face) for face in faces], style)
    i=max(range(sides), key=lambda j: dirs[j].x * side_sign)
    return (Vector(verts[i]) + Vector(verts[sides+i])) * .5

def build(g):
    n=8 if g.lod==0 else 6
    from fitting import Clothing
    from wraps import wrist_strap
    surface=Clothing()
    tree=sleeve_bvh()
    for side,sgn in [('L',1),('R',-1)]:
        region='yoke'
        def p(x,y,z):
            if region=='upper':
                adjust=np.interp(y,(-.18,-.145,-.095,-.05,.002),(.039,.021,.003,.014,.026) if sgn>0 else (.027,.014,.003,.010,.018))
                adjust *= (.13 if sgn>0 else .21)
            elif region=='fore':
                adjust=np.interp(y,(-.35,-.19),(-.003,-.003) if sgn>0 else (.002,.001))
            else:
                adjust=0
            return (sgn*(x-adjust),y,z)
        upper='Base Human'+side+'Upperarm'; fore='Base Human'+side+'Forearm1'
        shoulder=Vector(g.head(upper)); elbow=Vector(g.head(fore)); wrist=Vector(g.head('Base Human'+side+'Palm'))
        shoulder_axis=(elbow-shoulder).cross(Vector((0,0,-1))).normalized()
        if shoulder_axis.x*sgn < 0: shoulder_axis.negate()
        elbow_axis=(wrist-elbow).cross(Vector((0,0,1))).normalized()
        if elbow_axis.x*sgn < 0: elbow_axis.negate()
        sp=lambda d: shoulder+shoulder_axis*((.095 if sgn>0 else .102)+.54*(d-.140))
        ep=lambda d: elbow+elbow_axis*(.083+.54*(d-.110))
        g.part('shoulderYoke'+side,'Base Human'+side+'Collarbone')
        # Split, open shoulder swivel: the axis points laterally, with a dark bearing
        # and a smaller machined retaining cap. The back link is supplied by torso.
        # A narrow yoke visibly closes the gap to the rear shoulder support.
        g.beam(p(.245,.085,1.520),sp(.155),.018,.012,0,bevel=.002,ref=(0,0,1))
        g.rod(sp(.140),sp(.160),.029,1,n)
        region='upper'
        g.part('upperarm'+side,upper)
        g.rod(sp(.160),sp(.177),.033,1,n)
        g.rod(sp(.177),sp(.185),.027,0,n)
        g.rod(sp(.185),sp(.189),.010,7,n)
        g.beam(sp(.171),p(.330,.002,1.483),.022,.013,0,bevel=.002,ref=(0,0,1))
        # Thin shaped braces follow the outside of the sleeve.
        g.beam(p(.330,.002,1.483),p(.399,-.095,1.435),.026,.013,0,bevel=.003,ref=(0,0,1))
        g.beam(p(.399,-.095,1.435),p(.463,-.170,1.393),.031,.014,0,bevel=.003,ref=(0,0,1))
        g.beam(p(.343,-.006,1.462),p(.449,-.155,1.376),.010,.010,2,ref=(0,0,1))
        c=shoulder.lerp(elbow,.43)
        cuff=band(g,tree,c,elbow-shoulder,.084,.030,.005,1,20 if g.lod==0 else 16,sgn)
        # Outer cuff anchor bridges the rails without a solid sleeve.
        g.beam(cuff,p(.365,-.050,1.457),.016,.010,1,ref=(0,0,1))
        # Tapered gearbox fork: broad at the bearing, narrowing into the rail.
        g.rod(ep(.138),ep(.150),.028,2,n,r2=.023)
        g.beam(ep(.145),p(.410,-.116,1.429),.028,.011,2,bevel=.003,ref=(0,0,1))
        if g.lod==0:
            g.tube([p(.357,-.038,1.482),p(.387,-.080,1.462),p(.415,-.116,1.448)],.004,1,6)
            g.rod(p(.387,-.080,1.462),p(.397,-.080,1.462),.007,7,8)
        # Elbow drive is concentric with the forearm hinge, externally offset.
        g.rod(ep(.110),ep(.128),.036,1,n)
        g.rod(ep(.128),ep(.135),.028,0,n)
        g.rod(ep(.135),ep(.139),.010,7,n)
        g.beam(p(.463,-.170,1.393),ep(.119),.022,.012,0,bevel=.002,ref=(0,0,1))
        if g.lod==0:
            g.rod(p(.397,-.099,1.439),p(.408,-.099,1.439),.006,7,8)
            g.rod(p(.453,-.153,1.393),p(.465,-.153,1.393),.006,7,8)
        region='fore'
        g.part('forearm'+side,fore)
        # Mechanical link begins just beyond the pivot and stays outside the sleeve.
        g.beam(p(.426,-.188,1.379),p(.449,-.352,1.383),.030,.014,0,bevel=.003,ref=(0,0,1))
        g.beam(p(.430,-.199,1.408),p(.448,-.327,1.409),.009,.008,2,ref=(0,0,1))
        cuff=wrist_strap(g,surface,elbow,wrist,side)
        g.beam(cuff,p(.449,-.350,1.383),.016,.010,1,ref=(0,0,1))
        g.rod(ep(.128),ep(.135),.019,3,n)
        g.beam(ep(.131),p(.426,-.188,1.379),.018,.010,0,bevel=.002,ref=(0,0,1))
        if g.lod==0:
            g.tube([p(.447,-.222,1.415),p(.455,-.273,1.414),p(.458,-.315,1.412)],.004,1,6)
            g.rod(p(.455,-.273,1.414),p(.463,-.273,1.414),.006,7,8)
            # Short actuator and sliding rod, within the outer frame envelope.
            g.rod(p(.450,-.222,1.363),p(.460,-.290,1.365),.009,1,8)
            g.rod(p(.460,-.290,1.365),p(.466,-.329,1.367),.004,3,8)
            g.rod(p(.450,-.341,1.383),p(.459,-.341,1.383),.006,7,8)






