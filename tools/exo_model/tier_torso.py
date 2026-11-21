"""Tier 2/3 torso additions to the garment-fitted suspension."""
from mathutils import Vector
import torso

SPINE = 'Base HumanSpine3'
PELVIS = 'Base HumanPelvis'


def shell(g, outline, inner, outer, style):
    """Extruded chamfered outline, with closed front and rear faces."""
    n = len(outline)
    verts = [(x,y,z) for y in (inner,outer) for x,z in outline]
    faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)]
    g.mesh(verts,faces,style)


def build(g, tier):
    if tier not in (2, 3):
        raise ValueError('tier must be 2 or 3')
    old_cell = torso._cell
    try:
        torso._cell = lambda _: None
        torso.build(g)
    finally:
        torso._cell = old_cell
    advanced = tier == 3
    n = 8 if g.lod else 12
    # Crossbars and a keel physically join the rear cases to the original rails.
    g.part('powerMount', SPINE)
    for z in (1.195, 1.365):
        g.beam((-.115,.177,z),(.115,.177,z),.024,.023,0,.003,ref=(0,0,1))
        for x in (-.083,.083):
            g.beam((x,.177,z),(x,.184,z),.018,.018,0,.002,ref=(0,0,1))
    g.beam((0,.170,1.160),(0,.195,1.425),.035,.026,0,.004)
    for s in (-1,1):
        g.rod((s*.105,.183,1.195),(s*.133,.170,1.145),.009,0,n=6)
        g.rod((s*.092,.223,1.367),(s*.112,.205,1.409),.008,0,n=6)
    g.part('powerModules', SPINE)
    # Inboard cell lugs slide onto the two frame crossbars.
    for sign in (-1,1):
        g.beam((sign*.067,.141,1.212),(sign*.067,.187,1.212),
               .023,.018,7,.002,ref=(1,0,0))
    if advanced:
        outline=[(-.071,1.167),(.071,1.167),(.099,1.196),(.099,1.350),(.070,1.399),(-.070,1.399),(-.099,1.350),(-.099,1.196)]
        shell(g,outline,.180,.228,1)
        inset=[(-.054,1.180),(.054,1.180),(.082,1.207),(.082,1.340),(.057,1.382),(-.057,1.382),(-.082,1.340),(-.082,1.207)]
        shell(g,inset,.228,.236,0)
        # Recessed window sits below the surrounding rim and raised cooling ribs.
        g.box((0,.237,1.301),(.048,.003,.127),3,.001)
        g.box((0,.240,1.301),(.029,.003,.108),6,.001)
        for z in (1.207,1.225,1.243,1.359,1.377):
            g.box((0,.243,z),(.112,.012,.006),1,.001)
        for s in (-1,1):
            g.beam((s*.082,.198,1.340),(s*.105,.171,1.395),.021,.018,0,.002)
    else:
        for s in (-1,1):
            x=s*.058
            outline=[(x-.037,1.196),(x+.037,1.196),(x+.044,1.205),(x+.044,1.356),(x+.035,1.374),(x-.035,1.374),(x-.044,1.356),(x-.044,1.205)]
            shell(g,outline,.180,.225,1)
            g.box((x,.230,1.285),(.066,.010,.148),2,.004)
            for z in (1.203,1.365):
                g.box((x,.228,z),(.080,.012,.014),0,.002)
            g.beam((s*.106,.181,1.195),(s*.106,.213,1.375),.014,.014,0,.002)
            g.beam((s*.099,.226,1.325),(s*.116,.233,1.346),.010,.008,3,.001)
        # A single service label differentiates the removable cells.
        g.box((.058,.236,1.309),(.043,.003,.024),4,.001)
        for z in (1.303,1.309,1.315):
            g.box((.058,.239,z),(.026,.002,.002),7,0)
    for s, side in ((1, 'L'), (-1, 'R')):
        g.part('shoulderSupport' + side, SPINE)
        p0 = Vector((s*.105, .171, 1.395))
        p1 = Vector((s*.150, .178, 1.466))
        p2 = Vector((s*.195, .150, 1.504))
        p3 = Vector((s*.245, .085, 1.520))
        w = .031 if advanced else .026
        for a,b in ((p0,p1),(p1,p2),(p2,p3)):
            g.beam(a,b,w,.022,0,.003,ref=(0,0,1))
        g.rod(p2.lerp(p3,.38),p2.lerp(p3,.75),.022 if advanced else .017,1,n=n)
        g.rod(p2.lerp(p3,.75),p2.lerp(p3,.94),.010,3,n=8)
        g.tube([(s*.092,.223,1.367),(s*.112,.205,1.409),
                (s*.154,.191,1.464),(s*.196,.164,1.501),p3],
               .0055 if advanced else .0045,1,n=6)
        g.part('hipHousing' + side, PELVIS)
        pivot=Vector((s*.208,-.005,.9764))
        g.rod(pivot + Vector((s*.004,0,0)),pivot + Vector((s*.025,0,0)),
              .043 if advanced else .038,1,n=n)
        g.rod(pivot + Vector((s*.025,0,0)),pivot + Vector((s*.033,0,0)),
              .032 if advanced else .029,0,n=n)
        g.rod(pivot + Vector((s*.033,0,0)),pivot + Vector((s*.038,0,0)),.011,3,n=8)
        g.beam((s*.145,.105,1.047),(s*.200,.034,.995),.028,.022,0,.003,ref=(0,0,1))
        g.rod((s*.182,.086,1.045),(s*.193,.032,.994),.009,0,n=6)
        g.part('lumbarCable' + side, PELVIS)
        g.tube([(s*.105,.183,1.195),(s*.133,.170,1.145),
                (s*.156,.130,1.094),(s*.182,.086,1.045),
                (s*.193,.032,.994)], .006 if advanced else .005, 1, n=6,
               bones=(SPINE,PELVIS))
