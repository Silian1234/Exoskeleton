"""Contoured wrist suspension, sampled against the bind sleeve and skinned to the cloth."""
import math
from mathutils import Vector


def wrist_strap(g, cloth, elbow, wrist, side):
    axis=(wrist-elbow).normalized()
    vertical=Vector((0,0,1))
    vertical=(vertical-axis*axis.dot(vertical)).normalized()
    lateral=axis.cross(vertical)
    points=[]
    weights=[]
    # A slight diagonal clears the inside of the wrist as the hand drops past
    # the belt. The outside span stays level and sits under the rail latch.
    profiles={'L':{14:.75,15:.75},'R':{11:.75,12:.78,13:.78,14:.78,15:.75}}
    for i in range(24):
        t=profiles[side].get(i,.72)
        ray=vertical*math.cos(math.tau*i/24)+lateral*math.sin(math.tau*i/24)
        for dz in (-.006,.006):
            origin=elbow.lerp(wrist,t)+dz*axis
            hit=cloth.tree.ray_cast(origin,ray,.17)[0]
            points.append(hit+ray*.010)
            weights.append(cloth.skin(hit))
    faces=[]
    for i in range(24):
        a=2*i;b=2*((i+1)%24)
        faces.extend(((a,b,b+1),(a,b+1,a+1)))
    g.mesh(points,faces,5,weights)
    sign=1 if side=='L' else -1
    i=max(range(24),key=lambda k:points[2*k].x*sign)
    return (points[2*i]+points[2*i+1])*.5

def leg_webbing(g, cloth, sign, thigh):
    """Both edges of the strap track the garment and the knee fold.
    The fitted height profile is reproduced by the leg-wrap study.
    """
    n=32
    if thigh and sign>0:
        heights=[.724]*32
        heights[4:12]=[.736,.748,.784,.796,.796,.772,.748,.736]
        heights[28]=.736
    elif thigh:
        heights=[.712]*32
        heights[3:13]=[.724,.736,.760,.772,.784,.784,.772,.748,.736,.724]
    else:
        heights=[.250]*32
        if sign>0:
            heights[7:11]=[.238,.226,.226,.238]
    vs=[]; weights=[]; faces=[]
    for i,z in enumerate(heights):
        angle=math.tau*i/n
        ray=Vector((sign*math.cos(angle),math.sin(angle),0))
        cx=.178-.125*(z-.3)
        cy=-.024 if thigh else .039
        reach=min(.19,(cx-.002)/max(.001,-math.cos(angle)))
        for dz in (-.008,.008):
            center=Vector((sign*cx,cy,z+dz))
            hit=cloth.tree.ray_cast(center+ray*reach,-ray,reach)[0]
            vs.append(hit+.010*ray);weights.append(cloth.skin(hit))
    for i in range(n):
        a=2*i;b=2*((i+1)%n)
        faces.extend(((a,b,b+1),(a,b+1,a+1)))
    g.mesh(vs,faces,5,weights)
    return (vs[0]+vs[1])*.5
