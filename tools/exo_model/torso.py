"""Twin-rail back unit, removable cell and garment-fitted suspension harness."""
import math
from mathutils import Vector
from fitting import Clothing
import waist

SPINE = 'Base HumanSpine3'
PELVIS = 'Base HumanPelvis'


def _plate(g, outline, inner, outer, style):
    """Extrude an X/Z outline along the raked battery cradle."""
    slope = .22
    verts = [(x, y + slope * (z - 1.28), z) for y in (inner, outer) for x,z in outline]
    n = len(outline)
    faces = [tuple(reversed(range(n))), tuple(range(n,2*n))]
    faces.extend((i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n))
    g.mesh(verts,faces,style)


def _cell(g):
    outline=[(-.058,1.192),(-.041,1.175),(.034,1.175),(.058,1.201),
             (.058,1.360),(.038,1.387),(-.043,1.387),(-.058,1.371)]
    _plate(g,outline,.146,.17,1)
    _plate(g,outline,.167,.183,2)
    panel=[(-.044,1.205),(-.031,1.193),(.031,1.193),(.045,1.210),
           (.045,1.349),(.029,1.368),(-.034,1.368),(-.044,1.357)]
    _plate(g,panel,.183,.188,0)
    _plate(g,[(x*.91,1.28+(z-1.28)*.93) for x,z in panel],.188,.191,2)
    face = lambda z: .191+.22*(z-1.28)
    for side in (-1,1):
        # Rails capture the side lugs of the removable battery.
        for z in (1.212,1.350):
            g.beam((side*.050,face(z)-.029,z),(side*.074,face(z)-.037,z),
                   .019,.012,0,.002,ref=(0,0,1))
        for i in range(3 if g.lod else 6):
            z=1.217+.108*i/(2 if g.lod else 5)
            g.box((side*.059,face(z)-.017,z),(.011,.030,.004),0,.0012)
        z=1.355
        g.beam((side*.043,face(z)-.008,z-.010),(side*.048,face(z)+.002,z+.008),
               .009,.008,4,.0014)
    # Lower service connector is physically attached to the case.
    for x in (-.028,.024):
        g.rod((x,.155,1.185),(x,.155,1.168),.007,0,n=8)
        g.rod((x,.155,1.170),(x,.155,1.160),.0055,7,n=6)


def _ribbon(g, rows, style=5):
    verts=[]; weights=[]; faces=[]
    for left,right,wl,wr in rows:
        verts.extend((left,right)); weights.extend((wl,wr))
    for i in range(len(rows)-1):
        a=2*i
        faces.append((a,a+1,a+3,a+2))
    g.mesh(verts,faces,style,weights=weights)


def _fabric(surface,x,z,front=True,margin=.010):
    dy=-1 if front else 1
    point=surface.tree.ray_cast((x,dy*.55,z),(0,-dy,0))[0]
    if point is None:
        raise RuntimeError(f'Garment not found at {(x,z)}')
    return point+Vector((0,dy*margin,0)),surface.skin(point)


def _braces(g,surface,sign):
    # The path crosses the shoulder on its curved section and ends on the rear yoke.
    belt,skin=waist.station(surface,sign*(math.pi-.46),dr=.002)
    x0=abs(belt.x)
    rows=[]
    def add_row(samples):
        (left,wl),(right,wr)=samples
        rows.append((left,right,wl,wr))
    z_end=1.386
    steps=18 if not g.lod else 11
    for i in range(steps):
        t=i/steps; z=belt.z*(1-t)+z_end*t
        x=x0*(1-t)+.122*t
        points=[_fabric(surface,sign*(x+dx),z,margin=.012) for dx in (-.011,.011)]
        if 1.033 < z < 1.12:
            for pt,_ in points:
                pt.y=min(pt.y,-.151)
        if i==0:
            for j,(pt,_) in enumerate(points):
                pt.y=belt.y
                points[j]=(pt,skin)
        add_row(points)
    for i in range(21 if not g.lod else 13):
        count=20 if not g.lod else 12
        angle=math.pi*i/count
        direction=Vector((0,-math.cos(angle),math.sin(angle)))
        points=[]
        for dx in (-.011,.011):
            x=sign*(.122+dx)
            origin=Vector((x,.012,z_end))
            hit=surface.tree.ray_cast(origin+direction*.5,-direction)[0]
            if hit is None:
                raise RuntimeError('No shoulder strap hit')
            points.append((hit+direction*.012,surface.skin(hit)))
        add_row(points)
    _ribbon(g,rows)
    return rows


def _chest(g,surface):
    g.part('harness',SPINE)
    for s in (-1,1):
        _braces(g,surface,s)
    z=1.32
    # Ladder-lock frames clamp the longitudinal straps. The cross strap joins
    # their inner bars and curves to the sternum rather than bridging through it.
    strap_x=.109
    for s in (-1,1):
        x=s*strap_x
        rows=[]
        for dz in (-.015,.015):
            for dx in (-.016,.016):
                a,_=_fabric(surface,x+dx,z+dz,margin=.014)
                rows.append(a)
        for i,j in ((0,1),(1,3),(3,2),(2,0)):
            g.rod(rows[i],rows[j],.0025,7,n=6)
    rows=[]
    for i in range(15 if not g.lod else 9):
        count=14 if not g.lod else 8
        x=-strap_x+2*strap_x*i/count
        (a,wa),(b,wb)=[_fabric(surface,x,z+dz,margin=.015) for dz in (-.0075,.0075)]
        rows.append((a,b,wa,wb))
    _ribbon(g,rows)
    center,_=_fabric(surface,0,z,margin=.017)
    g.box(center,(.032,.007,.021),1,.002)
    g.box(center+Vector((-.006,-.004,0)),(.012,.004,.014),4,.001)


def build(g):
    surface=Clothing()
    g.part('back',SPINE)
    _cell(g)
    for s in (-1,1):
        p=[(s*.067,.148,1.165),(s*.073,.146,1.228),(s*.077,.148,1.322),
           (s*.095,.171,1.435),(s*.15,.169,1.475),(s*.190,.146,1.505),(s*.245,.085,1.520)]
        for i,(a,b) in enumerate(zip(p,p[1:])):
            g.beam(a,b,.016 if i<3 else .021,.012,0,.0025)
        # An open triangle takes up load between the shoulder and spine.
        g.beam(p[2],(s*.146,.168,1.443),.009,.010,2,.0015)
        g.beam((s*.146,.168,1.443),p[4],.011,.010,2,.0015)
        g.rod((s*.146,.163,1.443),(s*.146,.175,1.443),.007,7,n=8)
        g.tube([(s*.024,.155,1.163),(s*.033,.158,1.149),
                (s*.062,.152,1.153),p[0]],.0045,1,n=6)
        if not g.lod:
            g.tube([(s*.050,.183,1.363),(s*.064,.177,1.402),
                    (s*.087,.178,1.437),(s*.145,.176,1.475),p[5]],.0035,1,n=7)
            for x,y,z in (p[1],p[2],p[4]):
                g.rod((x,y+.003,z),(x,y+.010,z),.004,7,n=6)
    for x,y,z in ((.067,.148,1.165),(.078,.161,1.334),(.095,.171,1.435)):
        g.beam((-x,y,z),(x,y,z),.013,.010,0,.0015,ref=(0,0,1))
    # Two hat-section channels connect the cell rails to the belt. Weighted
    # flexible joints accommodate the pelvis turning beneath the rigid case.
    g.part('lumbar',PELVIS)
    for s in (-1,1):
        start,_=waist.station(surface,s*.56,dr=.002)
        end=Vector((s*.067,.148,1.165))
        mid=start.lerp(end,.50)+Vector((0,.017,0))
        g.tube([start,start.lerp(mid,.6),mid,mid.lerp(end,.55),end],
               .008,0,n=6,bones=(PELVIS,SPINE))
    _chest(g,surface)
    g.part('belt',PELVIS)
    v,f,w=waist.ribbon(surface,n=56 if g.lod else 72)
    g.mesh(v,f,5,weights=w)
    buckle,_=waist.station(surface,math.pi,dr=.004)
    g.box(buckle,(.046,.009,.023),1,.002)
    g.box(buckle+Vector((0,-.005,0)),(.024,.004,.014),4,.0015)
    for s,side in ((-1,'R'),(1,'L')):
        g.part('hipBridge'+side,PELVIS)
        at,_=waist.station(surface,s*math.pi*.47,dr=.002)
        pivot=Vector((s*.208,-.005,.9764))
        g.beam(at,pivot,.022,.010,0,.002,ref=(0,0,1))
        axis=Vector((s,0,.12)).normalized()
        g.rod(pivot-.009*axis,pivot-.002*axis,.021,2,n=8 if g.lod else 12)


