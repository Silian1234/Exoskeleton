"""Outboard transmission casings in the existing hip and knee assemblies."""
from math import cos, radians, sin
from mathutils import Vector


def casing(g, side, center, outline, depth, finish):
    """Cast side plate with a narrower, crowned service face."""
    origin = Vector(center)
    def point(axial, fore, up):
        return origin + Vector((side * axial, -fore, up))

    rings = [(0, .94), (.004, 1), (depth - .005, 1), (depth, .83)]
    if g.lod:
        rings = [(0, 1), (depth, .86)]
    n = len(outline)
    verts = [point(x, y*k, z*k) for x,k in rings for y,z in outline]
    faces = [tuple(reversed(range(n)))]
    styles = [1]
    for i in range(len(rings)-1):
        for j in range(n):
            a = i*n+j
            b = i*n+(j+1)%n
            faces.append((a,b,b+n,a+n))
            styles.append(finish if i+2 == len(rings) else 0)
    faces.append(tuple(range(len(verts)-n, len(verts))))
    styles.append(finish)
    g.mesh(verts, faces, styles)
    return point


def dial(g, point, tier, depth):
    """The rim and its central hex register stand proud of the removable cover."""
    n = 14 if not g.lod else 8
    if g.lod:
        g.rod(point(depth-.001,0,0), point(depth+.005,0,0), .021, 7, n)
        return
    g.rod(point(depth-.001,0,0), point(depth+.003,0,0), .025, 1, n)
    g.rod(point(depth+.002,0,0), point(depth+.006,0,0), .018, 7, n)
    g.rod(point(depth+.006,0,0), point(depth+.009,0,0), .010, 0, 6)
    # A partial enamel index ring and three installed flange screws.
    arc = [point(depth+.001, .029*cos(radians(a)), .029*sin(radians(a)))
           for a in range(30,121,10)]
    g.tube(arc, .0018, 6 if tier == 3 else 4, n=5)
    for y,z in ((-.027,.022), (.027,-.017), (-.012,-.033)):
        g.rod(point(depth-.002,y,z), point(depth+.003,y,z), .0037, 7, 6)


def build(g, tier):
    for side, sign in (('L',1),('R',-1)):
        for joint in ('hip','knee'):
            knee = joint == 'knee'
            if knee:
                g.part('kneeDrive' + side, 'Base Human' + side + 'Calf')
                center = (sign*.279, -.040, .524)
            else:
                g.part('hipHousing' + side, 'Base HumanPelvis')
                center = (sign*.235, -.005, .9764)
            if tier == 2:
                # Cast reduction cover and flat bolted inspection lid. Hip and
                # knee use the same bearing, with different gear-train outlines.
                outline = [(-.038,.022),(-.026,.043),(.019,.043),(.042,.022),
                           (.046,-.013),(.025,-.042),(-.013,-.058),(-.038,-.034)]
                if not knee:
                    outline = [(y,-z) for y,z in outline]
                depth = .019
                p = casing(g, sign, center, outline, depth, 2)
                dial(g, p, tier, depth)
                if not g.lod:
                    for y in (-.015,0,.015):
                        z = -.036 if knee else .036
                        g.beam(p(depth,y-.004,z),p(depth,y+.004,z),.004,.003,4)
            else:
                # A forward-swept case encloses the transmission, overhangs
                # its bearing, then tapers back to the frame below the joint.
                outline = [(-.039,.028),(-.018,.051),(.014,.049),(.043,.034),
                           (.057,.010),(.052,-.018),(.020,-.058),(-.009,-.088),
                           (-.022,-.081),(-.033,-.033)]
                if not knee:
                    outline = [(y*.93, -z*.83) for y,z in outline]
                depth = .026
                p = casing(g, sign, center, outline, depth, 4)
                dial(g, p, tier, depth)
                # Inlaid witness marks set the two service approaches apart.
                zdir = -1 if knee else 1
                g.beam(p(depth,.019,zdir*.033),p(depth,-.007,zdir*.062),
                       .0045,.004,6,ref=(1,0,0))
                if not g.lod:
                    for k in range(3):
                        y = -.021+k*.008
                        g.beam(p(depth+.0005,y,-zdir*.032),
                               p(depth+.0005,y+.006,-zdir*.024),.0035,.002,1)
