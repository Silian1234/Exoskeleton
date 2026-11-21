"""EXO-3 lateral leg assemblies, authored in world metres for EFT_Bind.
Call build(g) once for each LOD using the shared mesh builder.
"""

import bpy, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

def build(g, tier):
    from tier_drives import ram, rail_cover
    from tier_legs_cuff import leg_webbing, prepare
    prepare()
    lod = g.lod
    ref = bpy.data.objects['REF_pants']
    ev = ref.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    verts = [ev.matrix_world @ v.co for v in mesh.vertices]
    from fitting import Clothing
    cloth = Clothing()
    tris = []
    mesh.calc_loop_triangles()
    for tri in mesh.loop_triangles: tris.append(tuple(tri.vertices))
    tree = BVHTree.FromPolygons(verts, tris, all_triangles=True)
    ev.to_mesh_clear()
    def rail(s, sections):
        # Each station has lateral inner edge x, center y, height z, width, depth.
        # Eight-sided chamfered extrusion follows a measured profile.
        v=[]; faces=[]
        for x,y,z,w,d in sections:
            for xx,yy in ((0,-.32),(0,.32),(.22,.5),(.78,.5),(1,.32),(1,-.32),(.78,-.5),(.22,-.5)):
                v.append((s*(x+xx*d),y+yy*w,z))
        faces.append(tuple(reversed(range(8))))
        for i in range(len(sections)-1):
            for j in range(8): faces.append((i*8+j,i*8+(j+1)%8,(i+1)*8+(j+1)%8,(i+1)*8+j))
        faces.append(tuple((len(sections)-1)*8+j for j in range(8)))
        # Cap triangulation avoids n-gons in the exported asset.
        faces=faces[1:-1]+[(0,1,2,3),(0,3,4,5),(0,5,6,7),
             tuple((len(sections)-1)*8+j for j in (0,3,2,1)),
             tuple((len(sections)-1)*8+j for j in (0,5,4,3)),
             tuple((len(sections)-1)*8+j for j in (0,7,6,5))]
        g.mesh(v,faces,style=0)
    # Derive required rest-space rail offsets against every deformed garment.
    import review
    posed = {}
    for pose in ('rest','crouch','knee120'):
        review.set_pose(pose)
        dep = bpy.context.evaluated_depsgraph_get()
        vv,tt=review._mesh(ref,dep)
        bt=BVHTree.FromPolygons(vv,tt,all_triangles=True)
        for sd in ('L','R'):
            for bone in ('Thigh1','Calf'):
                name='Base Human'+sd+bone
                mat=review.ARM.matrix_world @ review.ARM.pose.bones[name].matrix @ review.ARM.data.bones[name].matrix_local.inverted() @ review.ARM.matrix_world.inverted()
                posed[(pose,sd,bone)] = (bt,mat,mat.inverted())
    review.set_pose('rest')
    for side, s in (('L', 1), ('R', -1)):
        def P(x,y,z): return (s*x,y,z)
        def surface(y,z):
            hit,normal,idx,d=tree.ray_cast(Vector((s*.55,y,z)),Vector((-s,0,0)),.50)
            if hit is None: raise RuntimeError('No lateral garment at %s %s' % (y,z))
            return abs(hit.x)
        def rod(a,b,r,style=0): g.rod(P(*a),P(*b),r,style=style,n=6)
        def beam(a,b,w,d,style=0): g.beam(P(*a),P(*b),w,d,style=style,bevel=.001,ref=(0,1,0))
        def axle(x,y,z,r,style=0):
            # Axle follows the world-space hinge axis, not horizontal X.
            g.rod(P(x-.006,y,z-.0007),P(x+.008,y,z+.0009),r,style,n=(16 if lod==0 else 8) if r>=.015 else 6)
        thigh='Base Human'+side+'Thigh1'; calf='Base Human'+side+'Calf'; foot='Base Human'+side+'Foot'
        # The rotational axes pass through each named bone head and are tilted
        # by the limb vector. Every piece sharing an axis can rotate about it.
        hip=(.208,-.005,.9764); knee=(.250,-.040,.5239); ankle=(.284,.056,.073)
        def make_sections(spec,bone):
            result=[]
            for z,y,w in spec:
                need=surface(y,z)+.009
                for pose in ('rest','crouch','knee120'):
                    bt,mat,inv=posed[(pose,side,bone)]
                    for dz in (-.014,0,.014):
                        for dy in (-w*.5,0,w*.5):
                            start=mat @ Vector((s*.55,y+dy,z+dz))
                            direction=mat.to_3x3() @ Vector((-s,0,0))
                            hit,normal,idx,d=bt.ray_cast(start,direction.normalized(),.50)
                            if hit is not None:
                                rest=inv @ hit
                                if 0<rest.x*s<.50: need=max(need,rest.x*s+.010)
                
                if side=='R' and bone=='Thigh1': need += .012
                result.append((need,y,z,w * (1.6 if tier==2 else 1.9), .028 if tier==2 else .034))
            return result
        # Rail sections trace the lateral garment with their undersides at +7 mm.
        upper=make_sections([(.895,-.015,.025),(.850,-.020,.030),(.790,-.025,.033),(.730,-.035,.031),(.670,-.030,.028),(.600,-.025,.027),(.555,-.030,.025)],'Thigh1')
        upper=[(hip[0],hip[1],hip[2],.040,.028 if tier==2 else .034)]+upper+[(knee[0],knee[1],knee[2],.026,.012)]
        lower=make_sections([(.475,.000,.026),(.425,.025,.029),(.370,.040,.030),(.310,.050,.030),(.250,.045,.026),(.200,.030,.025),(.150,.030,.024),(.110,.040,.022)],'Calf')
        lower=[(knee[0],knee[1],knee[2],.040,.028 if tier==2 else .034)]+lower+[(ankle[0],ankle[1],ankle[2],.023,.012)]
        def skin_rail(sections):
            rail(s,sections)
            rail_cover(g,side,sections,tier)
        g.part('thigh'+side,thigh); skin_rail(upper)
        axle(*hip,.026,1); axle(hip[0]+.010,hip[1],hip[2]+.001,.016,0)
        leg_webbing(g,cloth,s,True,side); g.part('thigh'+side,thigh)
        if lod==0:
            # Brackets and pins derive from the same contiguous surface profile.
            for j in (2,4,6):
                x,y,z,w,d=upper[j]; axle(x+d+.003,y,z,.004,7)
            a,b=upper[2],upper[5]
            p=(a[0]+a[4]+.005,a[1]+.015,a[2]); q=(b[0]+b[4]+.005,b[1]+.015,b[2]);
            beam((a[0]+a[4],a[1],a[2]),p,.009,.008,0)
            beam((b[0]+b[4],b[1],b[2]),q,.009,.008,0)
            mid=tuple(p[i]*.56+q[i]*.44 for i in range(3))
            rod(p,mid,.008,1); rod(mid,q,.0035,3)
            beam((a[0]+a[4]+.003,a[1]-.003,a[2]-.025),
                 (a[0]+a[4]+.003,a[1]-.003,a[2]-.070),.025,.012,2)
            g.tube([P(*p),P(p[0]+.008,p[1]+.012,p[2]-.016),P(mid[0]+.010,mid[1]+.010,mid[2])],.0025,style=1,n=4)
        ram(g,side,'hip',upper,hip,tier)
        g.part('knee'+side,calf)
        axle(*knee,.029,1); axle(knee[0]+.010,knee[1],knee[2]+.001,.020,0); axle(knee[0]+.018,knee[1],knee[2]+.002,.008,3)
        # Eccentric lever shares the calf joint and terminates on its lower rail.
        crank=(knee[0]+.016,knee[1]+.024,knee[2]-.022)
        axle(crank[0],crank[1],crank[2],.007,7)
        beam((knee[0]+.020,knee[1],knee[2]),crank,.012,.008,0)
        c=lower[1]
        beam(crank,(c[0]+c[4],c[1],c[2]),.009,.007,0)
        g.part('shin'+side,calf); skin_rail(lower)
        ram(g,side,'knee',lower,knee,tier)
        axle(knee[0]+.025,knee[1],knee[2],.042,1)
        axle(knee[0]+.035,knee[1],knee[2],.028,2)
        g.part('shin'+side,calf)
        leg_webbing(g,cloth,s,False,side); g.part('shin'+side,calf)
        if lod==0:
            for j in (2,4,6):
                x,y,z,w,d=lower[j]; axle(x+d+.003,y,z,.004,7)
            a,b=lower[2],lower[5]
            p=(a[0]+a[4]+.005,a[1]+.014,a[2]); q=(b[0]+b[4]+.005,b[1]+.014,b[2]);
            beam((a[0]+a[4],a[1],a[2]),p,.009,.008,0)
            beam((b[0]+b[4],b[1],b[2]),q,.009,.008,0)
            mid=tuple(p[i]*.56+q[i]*.44 for i in range(3))
            rod(p,mid,.008,1); rod(mid,q,.0035,3)
            beam((a[0]+a[4]+.003,a[1]-.003,a[2]-.018),
                 (a[0]+a[4]+.003,a[1]-.003,a[2]-.064),.025,.012,2 if side=='L' else 4)
            g.tube([P(*p),P(p[0]+.008,p[1]+.012,p[2]-.016),P(mid[0]+.010,mid[1]+.010,mid[2])],.0025,style=1,n=4)
            if side=='L':
                # Marking pad is part of the asymmetric left service housing.
                beam((a[0]+a[4]+.011,a[1]-.005,a[2]-.026),
                     (a[0]+a[4]+.011,a[1]-.005,a[2]-.054),.014,.003,4)
        g.part('foot'+side,foot)
        axle(*ankle,.022,1); axle(ankle[0]+.010,ankle[1],ankle[2]+.001,.015,0)
        from boots import cradle
        cradle(g,tree,s,Vector(P(*ankle)))
        # Reinforced lateral boot frame attached to the existing sole cradle.
        beam((ankle[0]+.012,ankle[1],ankle[2]),(.310,-.005,.052),.025,.012,2)
        beam((.310,-.005,.052),(.303,-.100,.042),.023,.011,2)
        axle(.310,-.005,.052,.006,3)
        axle(.303,-.100,.042,.006,3)

