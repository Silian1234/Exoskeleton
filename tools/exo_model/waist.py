"""Contoured load-bearing belt and the short links to both hip bearings."""
import math
from mathutils import Vector


def station(surface, angle, z_offset=0, dr=0, z0=1.00, pitch=.030, gap=.010):
    direction=Vector((math.sin(angle),math.cos(angle),0))
    z=z0+pitch*direction.y+z_offset+.066*max(0,-direction.y)**8
    origin=Vector((0,-.005,z))
    point,_,_,_=surface.tree.ray_cast(origin+direction*.5,-direction)
    if point is None:
        raise ValueError(f'No waist reference at {angle}, {z}')
    return point+direction*(gap+dr),surface.skin(point)


def ribbon(surface, n=64, z0=1.00, pitch=.030, gap=.010, half_height=.011):
    v=[]; weights=[]; faces=[]
    for i in range(n):
        for dz,dr in ((-half_height,0),(half_height,0),(half_height,.003),(-half_height,.003)):
            point,skin=station(surface,math.tau*i/n,dz,dr,z0,pitch,gap)
            v.append(point); weights.append(skin)
    for i in range(n):
        a,b=i*4,((i+1)%n)*4
        for j in range(4):
            faces.append((a+j,b+j,b+(j+1)%4,a+(j+1)%4))
    return v,faces,weights

