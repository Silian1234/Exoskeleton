"""Heavy articulated arm assemblies for tier 2 and tier 3.

The elbow actuator spans the forearm-mounted gland and the upper-arm crank eye.
"""
from math import cos, pi, sin
from mathutils import Vector
from arms import sleeve_bvh


def _slotted_link(g, a, b, sign, tier):
    """Hollow cheek of the upper arm link, with return walls in the milled slot."""
    direction = b-a
    axis = direction.normalized()
    up = Vector((0,0,1))
    up = (up-axis*up.dot(axis)).normalized()
    outer = axis.cross(up).normalized()
    if outer.x*sign < 0:
        outer.negate()
    length = direction.length
    shell = [(.00,.008),(.07,.018),(.75,.018),(.99,.006),
             (1.,-.008),(.88,-.017),(.16,-.029),(.00,-.016)]
    window = [(.14,.002),(.19,.008),(.66,.008),(.83,.002),
              (.82,-.003),(.75,-.006),(.24,-.014),(.14,-.009)]
    def point(t, z, depth):
        return a+axis*(t*length)+up*z+outer*depth
    verts = [point(t,z,x) for x,profile in ((.006,shell),(.015,shell),
                                            (.006,window),(.015,window))
             for t,z in profile]
    faces,styles=[],[]
    for i in range(8):
        j=(i+1)%8
        for face,style in (((i,j,8+j,8+i),0),((16+i,24+i,24+j,16+j),1),
                           ((8+i,8+j,24+j,24+i),4 if tier==3 else 2),
                           ((i,16+i,16+j,j),0)):
            faces.append(face)
            styles.append(style)
    g.mesh(verts,faces,styles)
    if not g.lod:
        for t in (.075,.91):
            g.rod(point(t,0,.014),point(t,0,.019),.0045,7,n=6)


def _cuff(g, tree, center, axis, sign, width, fallback):
    c, d = Vector(center), Vector(axis).normalized()
    u = Vector((0, 0, 1)); u = (u-d*u.dot(d)).normalized()
    v = d.cross(u).normalized()
    n = 16 if g.lod == 0 else 12
    rays = [u*cos(2*pi*i/n)+v*sin(2*pi*i/n) for i in range(n)]
    radii = []
    for ray in rays:
        samples = []
        for a in (-width/2, 0, width/2):
            hit = tree.ray_cast(c+d*a, ray, .22)[0]
            if hit is not None and (hit-(c+d*a)).length < fallback*1.5:
                samples.append((hit-(c+d*a)).length)
        radii.append(max(samples) if samples else fallback)
    radii = [(max(radii[(i-1)%n],radii[i],radii[(i+1)%n])+.015)/cos(pi/n) for i in range(n)]
    vertices = [c+d*a+ray*(r+extra) for a,extra in ((-width/2,0),(width/2,0),(-width/2,.006),(width/2,.006)) for ray,r in zip(rays,radii)]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        if rays[i].x*sign < .15 or rays[j].x*sign < .15:
            continue
        faces.extend(((i,j,n+j,n+i),(2*n+j,2*n+i,3*n+i,3*n+j),(i,2*n+i,2*n+j,j),(n+j,3*n+j,3*n+i,n+i)))
    active=[i for i in range(n) if rays[i].x*sign >= .15 and rays[(i+1)%n].x*sign >= .15]
    for i in active:
        j=(i+1)%n
        if (i-1)%n not in active:
            faces.append((i,n+i,3*n+i,2*n+i))
        if j not in active:
            faces.append((j,2*n+j,3*n+j,n+j))
    g.mesh(vertices,faces,1)
    # Narrow rigid retainer follows the outside of the sleeve and overlaps the shell.
    # It remains open on the body side to clear the torso in the arms-down pose.
    strap_width=.010
    strap_limit=.15 if fallback < .08 else -.2
    sv=[c+d*a+ray*(r+extra) for a,extra in ((-strap_width/2,0),(strap_width/2,0),(-strap_width/2,.003),(strap_width/2,.003)) for ray,r in zip(rays,radii)]
    sf=[]
    for i in range(n):
        j=(i+1)%n
        if rays[i].x*sign < strap_limit or rays[j].x*sign < strap_limit:
            continue
        sf.extend(((i,j,n+j,n+i),(2*n+j,2*n+i,3*n+i,3*n+j),(i,2*n+i,2*n+j,j),(n+j,3*n+j,3*n+i,n+i)))
    strap_active=[i for i in range(n) if rays[i].x*sign >= strap_limit and rays[(i+1)%n].x*sign >= strap_limit]
    for i in strap_active:
        j=(i+1)%n
        if (i-1)%n not in strap_active: sf.append((i,n+i,3*n+i,2*n+i))
        if j not in strap_active: sf.append((j,2*n+j,3*n+j,n+j))
    g.mesh(sv,sf,2)
    i=max(range(n),key=lambda k:rays[k].x*sign)
    anchor=(vertices[2*n+i]+vertices[3*n+i])*.5
    g.box(anchor+Vector((sign*.006,0,0)),(.016,.027,.022),2,bevel=.002)
    if not g.lod:
        g.beam(anchor+Vector((sign*.012,0,-.008)),anchor+Vector((sign*.020,0,.018)),
               .009,.006,7,.001,ref=(0,1,0))
    return anchor


def build(g, tier):
    if tier not in (2,3):
        raise ValueError('tier must be 2 or 3')
    tree=sleeve_bvh()
    n=8 if g.lod==0 else 6
    for side,s in (('L',1),('R',-1)):
        p=lambda x,y,z: Vector((s*x,y,z))
        upper='Base Human'+side+'Upperarm'
        fore='Base Human'+side+'Forearm1'
        shoulder=Vector(g.head(upper)); elbow=Vector(g.head(fore)); wrist=Vector(g.head('Base Human'+side+'Palm'))
        sa=(elbow-shoulder).cross(Vector((0,0,-1))).normalized()
        if sa.x*s<0: sa.negate()
        ea=(wrist-elbow).cross(Vector((0,0,1))).normalized()
        if ea.x*s<0: ea.negate()
        sp=lambda d: shoulder+sa*d
        ep=lambda d: elbow+ea*d
        def beam(a,b,w,d,style=0):
            g.beam(a,b,w,d,style,bevel=.003,ref=(0,0,1))
        def rod(a,b,r,style=0):
            g.rod(a,b,r,style,n)
        # Collar attachment and rotating bearing share the same axis.
        g.part('shoulderYoke'+side,'Base Human'+side+'Collarbone')
        beam(p(.245,.085,1.520),sp(.104),.020,.014,2)
        rod(sp(.095),sp(.112),.037,1)
        g.part('upperarm'+side,upper)
        rod(sp(.112),sp(.132),.041 if tier==3 else .036,1)
        rod(sp(.132),sp(.138),.027,2)
        rod(sp(.138),sp(.142),.010,7)
        a=p(.345,.002,1.483); b=p(.414,-.095,1.435); c=p(.478,-.170,1.393)
        beam(sp(.121)+Vector((-s*.006,.006,-.003)),a+Vector((-s*.006,.006,-.003)),.035,.020,2)
        beam(a,b,.039 if tier==2 else .044,.020,2)
        beam(b,c,.039 if tier==2 else .044,.020,2)
        _slotted_link(g, a, b.lerp(c,.52), s, tier)
        cuff=_cuff(g,tree,shoulder.lerp(elbow,.43)+Vector((0,.010,0)),elbow-shoulder,s,.042,.085)
        beam(cuff,p(.365,-.050,1.457),.022,.014,1)
        rod(ep(.083),ep(.110),.040,1)
        rod(ep(.110),ep(.118),.029,2)
        rod(ep(.118),ep(.123),.010,7)
        beam(c,ep(.100),.031,.017,2)
        # Eccentric point on the elbow crank is carried by the upper arm.
        crank=ep(.127)+Vector((0,.025,.020))
        beam(ep(.113),crank,.018,.012,2)
        rod(crank-ea*.007,crank+ea*.008,.012,1)
        if tier==3:
            # Separate shoulder drive casing rather than a decorative straight rail.
            rod(sp(.104),sp(.131),.049,1)
            beam(sp(.125),p(.351,-.027,1.467),.052,.025,1)
            beam(p(.337,-.012,1.498),p(.359,-.043,1.481),.007,.004,6)
        g.part('forearm'+side,fore)
        rod(ep(.110),ep(.120),.023,3)
        front=p(.444,-.188,1.379); end=p(.467,-.352,1.383)
        beam(ep(.115),front,.029,.017,2)
        beam(front,end,.040 if tier==2 else .045,.020,2)
        cuff=_cuff(g,tree,elbow.lerp(wrist,.72)+Vector((s*.020,0,0)),wrist-elbow,s,.035,.065)
        beam(cuff,p(.467,-.318,1.383),.022,.014,1)
        # End lug visibly terminates at the wrist, with its own hinge cap.
        beam(end,p(.469,-.376,1.383),.026,.014,2)
        rod(p(.460,-.376,1.383),p(.481,-.376,1.383),.015,1)
        barrel_end=p(.484,-.307,1.404)
        barrel_start=barrel_end.lerp(crank,.58)
        ram_dir=(crank-barrel_end).normalized()
        rod(barrel_start,barrel_end,.014 if tier==2 else .016,1)
        rod(barrel_start-ram_dir*.006,barrel_start+ram_dir*.002,.015,7)
        g.tube([barrel_start-ram_dir*.004,crank],.007,3,n=n,bones=(fore,upper))
        beam(barrel_end,p(.461,-.304,1.383),.018,.012,2)
        if tier==3:
            # Shaped housing includes the motor at the elbow and barrel shroud.
            rod(ep(.115),ep(.140),.046,1)
            beam(ep(.128),p(.477,-.230,1.407),.051,.027,1)
            beam(p(.477,-.230,1.407),p(.484,-.310,1.407),.037,.025,1)
            beam(p(.496,-.240,1.418),p(.501,-.292,1.418),.006,.004,6)
        if g.lod==0:
            rod(p(.452,-.300,1.405),p(.464,-.300,1.405),.006,7)









