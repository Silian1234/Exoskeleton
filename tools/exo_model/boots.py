"""Open boot cradle. A sole stirrup, heel cup and two edge runners follow the boot."""
import math
from mathutils import Vector


def cradle(g, tree, sign, ankle):
    n=24 if not g.lod else 16
    center=Vector((sign*.223,-.101,.027))
    vs=[]; faces=[]; styles=[]
    for i in range(n):
        angle=math.tau*i/n
        direct=Vector((sign*math.cos(angle),0,math.sin(angle)))
        for width,dr in ((-.009,.009),(.009,.009),(.009,.012),(-.009,.012)):
            origin=center+Vector((0,width,0))
            hit=tree.ray_cast(origin+direct*.106,-direct,.106)[0]
            if hit is None:
                raise RuntimeError(f'Missing boot stirrup section at {angle:.3f}')
            point=hit+dr*direct
            if i>n//2:
                # The outsole has a square welt. Follow its side face to the
                # bottom before crossing the tread, rather than chord-cutting it.
                walls=[]
                for lateral in (-1,1):
                    ray=Vector((sign*lateral,0,0))
                    edge=[]
                    for height in (.008,.018,.028):
                        base=Vector((center.x,origin.y,height))
                        wall=tree.ray_cast(base+ray*.12,-ray,.12)[0]
                        if wall is not None:
                            edge.append(wall.x*sign)
                    walls.append((min(edge)-dr) if lateral<0 else (max(edge)+dr))
                t=(i-n/2)/(n/2)
                across=max(0,min(1,2*t-.5))
                rise=max(0,1-4*t,4*t-3)
                point.x=sign*(walls[0]+across*(walls[1]-walls[0]))
                point.z=(-.005-dr)*(1-rise)+center.z*rise
            vs.append(point)
    for i in range(n):
        a=i*4;b=((i+1)%n)*4
        for k in range(4):
            faces.append((a+k,b+k,b+(k+1)%4,a+(k+1)%4))
            styles.append(5 if 0<i<n//2-1 else 1)
    g.mesh(vs,faces,styles)
    # At the two side anchors the stirrup connects to contoured sole runners.
    ends=[(vs[0]+vs[1])*.5,(vs[2*n]+vs[2*n+1])*.5]
    upper=[]
    for idx,edge in enumerate(ends):
        direction=Vector((sign*(1 if idx==0 else -1),0,0)); path=[edge]
        for y,z in ((-.070,.028),(-.020,.032),(.025,.035),(.063,.042)):
            origin=Vector((sign*.215,y,z))
            hit=tree.ray_cast(origin+direction*.131,-direction,.131)[0]
            if hit is None:raise ValueError('Runner missed boot')
            path.append(hit+direction*.013)
        for a,b in zip(path,path[1:]):
            g.beam(a,b,.013,.007,0,.0015,ref=(0,0,1))
        upper.append(path[-1])
    # U-shaped rear cup leaves both the toe and the boot upper exposed.
    center=Vector((sign*.215,.063,.044))
    vs=[];faces=[]; count=12 if not g.lod else 8
    for i in range(count+1):
        angle=math.pi*i/count;ray=Vector((sign*math.cos(angle),math.sin(angle),0))
        for dz,dr in ((-.008,.010),(.008,.010),(.008,.014),(-.008,.014)):
            origin=center+Vector((0,0,dz))
            hit=tree.ray_cast(origin+ray*.135,-ray,.135)[0]
            if hit is None:raise RuntimeError('Heel cup missed boot')
            vs.append(hit+ray*dr)
    for i in range(count):
        for j in range(4):
            faces.append((4*i+j,4*i+(j+1)%4,4*i+4+(j+1)%4,4*i+4+j))
    faces.extend(((0,3,2,1),tuple(4*count+i for i in range(4))))
    g.mesh(vs,faces,1)
    g.beam(ankle,upper[0],.023,.010,0,.002,ref=(0,1,0))
