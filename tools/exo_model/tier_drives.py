"""Skinned eye-to-gland rams and formed rail covers for the leg transmissions."""
from mathutils import Vector


def ram(g, side, joint, stations, pivot, tier):
    sign = 1 if side == 'L' else -1
    proximal = 'Base HumanPelvis' if joint == 'hip' else 'Base Human'+side+'Thigh1'
    distal = 'Base Human'+side+('Thigh1' if joint == 'hip' else 'Calf')
    name = joint+'Drive'+side
    axial = Vector((sign, 0, .12)).normalized()
    def coords(x,y,z):
        return Vector((sign*x,y,z))
    x,y,z = pivot
    # The pin is eccentric to the rotary shaft. Its location follows the input
    # half of the joint while the cylinder and guide bush follow the limb rail.
    reversed_mount = side=='R' and joint=='hip'
    clearance = .023 if reversed_mount else 0
    forward = -1 if reversed_mount else 1
    hub = coords(x+.023+clearance,y,z+.003)
    eye = hub+Vector((sign*.002,forward*.019,.004))
    a,b = stations[2],stations[5]
    top = coords(a[0]+.002, a[1], a[2])
    shoe = coords(b[0]+.002, b[1], b[2])
    base = coords(b[0]+b[4]+.010+clearance, b[1]+forward*.034, b[2])
    gland = base.lerp(eye, .61)
    direction = (gland-base).normalized()
    n = 12 if not g.lod else 6
    g.part(name, distal)
    g.beam(shoe, base, .026,.017,0,.003,ref=(0,0,1))
    g.beam(top, gland-.023*direction, .022,.015,0,.002,ref=(0,0,1))
    g.rod(base-.006*direction,gland,.017 if tier==2 else .019, 2 if tier==2 else 1,n)
    g.rod(gland-.008*direction,gland+.003*direction,.0185,7,n)
    if not g.lod:
        g.rod(base,base+.012*direction,.0195,1,n)
        g.rod(gland+.003*direction,gland+.006*direction,.011,1,n)
        g.rod(base-.010*axial,base+.013*axial,.011,7,8)
    # Two skinned rings form a straight polished span between the pins. The
    # distal end starts inside the gland and the proximal end inside the eye.
    # This keeps both interfaces seated without adding bones, constraints or IK.
    g.tube([gland-.007*direction,eye],.0065,3,n=8 if not g.lod else 5,
           bones=(distal,proximal))
    g.part(name, proximal)
    if reversed_mount:
        # A longer shoulder pin puts the rod on the clear side of the cargo pocket.
        g.rod(hub-clearance*axial,hub,.010,7,n)
    g.beam(hub,eye,.018,.012,0,.002,ref=axial)
    g.rod(eye-.008*axial,eye+.008*axial,.011,7,n)
    g.part(name, distal)
    if tier==3:
        sidewall = Vector((sign*.012,0,0))
        g.beam(base+sidewall,gland+sidewall,.043,.024,4,.004,ref=(0,1,0))
        g.beam(base.lerp(gland,.20)+1.78*sidewall,
               base.lerp(gland,.83)+1.78*sidewall,.004,.005,6,ref=(0,1,0))


def rail_cover(g, side, stations, tier):
    """A folded inspection channel follows the structural rail at its outer face."""
    sign = 1 if side=='L' else -1
    verts = []
    colors = []
    faces = []
    run = stations[1:-1]
    if g.lod:
        run = run[::2] if len(run)%2 else run[::2]+[run[-1]]
    for i,(x,y,z,w,d) in enumerate(run):
        t = i/(len(run)-1)
        # The advanced fairing sweeps toward the front of the leg at its broad
        # end; the service opening remains on the aft side, beside the piston.
        width = (.047 if tier==2 else .081) * (.52+.48*(1-t))
        nose = -.006 if tier==2 else -.013
        section = [(d-.009, .010), (d-.009, nose-width*.47),
                   (d+.003,nose-width*.55), (d+.012,nose-width*.27),
                   (d+.012,.009), (d+.005,.014)]
        for xx,yy in section:
            verts.append((sign*(x+xx),y+yy,z))
    faces.append(tuple(range(5,-1,-1)))
    colors.append(1)
    for i in range(len(run)-1):
        for j in range(6):
            a=i*6+j
            b=i*6+(j+1)%6
            faces.append((a,b,b+6,a+6))
            colors.append(([0,1,4,2,0,1] if tier==2 else [0,1,0,4,2,1])[j])
    faces.append(tuple(range(len(verts)-6,len(verts))))
    colors.append(1)
    g.mesh(verts,faces,colors)
