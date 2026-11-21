"""Build both rigid plate LODs over the unmodified, shipped second-tier frame.

blender -b exo_t3.blend --python-exit-code 1 --python build_t3a.py
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def surface_tree(objects):
    verts, tris = [], []
    for obj in objects:
        offset = len(verts)
        mesh = obj.data
        mesh.calc_loop_triangles()
        verts.extend(obj.matrix_world @ v.co for v in mesh.vertices)
        tris.extend(tuple(offset + k for k in tri.vertices) for tri in mesh.loop_triangles)
    return BVHTree.FromPolygons(verts, tris, all_triangles=True)


class Sheet:
    """Continuous parametrization of the stamped outer surface and its normals."""

    def __init__(self, rows, outward):
        self.points = [[Vector(p) for p in row] for row in rows]
        self.h = len(rows)
        self.w = len(rows[0])
        if min(self.w, self.h) < 2 or any(len(row) != self.w for row in rows):
            raise ValueError("Panel requires a rectangular grid")
        normals = []
        for j in range(self.h):
            band = []
            for i in range(self.w):
                across = self.points[j][min(i+1,self.w-1)]-self.points[j][max(i-1,0)]
                along = self.points[min(j+1,self.h-1)][i]-self.points[max(j-1,0)][i]
                band.append(across.cross(along).normalized())
            normals.append(band)
        self.flip = normals[self.h//2][self.w//2].dot(Vector(outward)) < 0
        self.normals = [[-v if self.flip else v for v in row] for row in normals]
        mid = self.points[self.h//2]
        self.width = sum((b-a).length for a,b in zip(mid,mid[1:]))
        mid = [row[self.w//2] for row in self.points]
        self.length = sum((b-a).length for a,b in zip(mid,mid[1:]))

    def sample(self, u, v, offset=0):
        x = max(0, min(1, u)) * (self.w-1)
        y = max(0, min(1, v)) * (self.h-1)
        i, j = min(int(x),self.w-2), min(int(y),self.h-2)
        x, y = x-i, y-j
        def interpolate(grid):
            return grid[j][i].lerp(grid[j][i+1],x).lerp(
                grid[j+1][i].lerp(grid[j+1][i+1],x),y)
        normal = interpolate(self.normals).normalized()
        return interpolate(self.points)+normal*offset, normal


class Plate:
    def __init__(self, sheet, lod):
        self.sheet, self.lod = sheet, lod
        self.verts, self.faces, self.finishes = [], [], []

    def point(self, p):
        self.verts.append(tuple(p))
        return len(self.verts)-1

    def face(self, indices, finish, flip=False):
        self.faces.append(tuple(reversed(indices)) if flip else tuple(indices))
        self.finishes.append(finish)

    def join_rings(self, a, b, finish, flip=False):
        for i,k in zip(range(len(a)), [*range(1,len(a)),0]):
            self.face([a[k],a[i],b[i],b[k]], finish, flip)

    def shell(self, thickness):
        s = self.sheet
        def retained(lines, count):
            indices=list(range(len(lines)))
            while len(indices)>count:
                costs=[]
                for k in range(1,len(indices)-1):
                    a,m,b=indices[k-1:k+2]
                    t=(m-a)/(b-a)
                    error=max((p-pa.lerp(pb,t)).length for pa,p,pb in zip(lines[a],lines[m],lines[b]))
                    costs.append((error,k))
                del indices[min(costs)[1]]
            return [i/(len(lines)-1) for i in indices]
        uvalues=retained(list(zip(*s.points)), (5 if s.width < .080 else 6) if self.lod else s.w)
        vvalues=retained(s.points, 5 if self.lod else s.h)
        us, vs = len(uvalues), len(vvalues)
        boundary = [(i,0) for i in range(us)] + [(us-1,j) for j in range(1,vs)] + [
            (i,vs-1) for i in range(us-2,-1,-1)] + [(0,j) for j in range(vs-2,0,-1)]
        def vertex(i,j,margin,depth):
            u,v = uvalues[i],vvalues[j]
            # Machine off each square corner ahead of the bevel.
            if i in (0,us-1) and j in (0,vs-1):
                u += (1-2*u)*min(.055,.0035/max(.015,s.width))
                v += (1-2*v)*min(.055,.0035/max(.015,s.length))
            u += (1-2*u)*min(.095,margin/max(.015,s.width))
            v += (1-2*v)*min(.095,margin/max(.015,s.length))
            return self.point(s.sample(u,v,depth)[0])
        def grid(margin, depth, finish, reverse=False):
            idx = [[vertex(i,j,margin,depth) for i in range(us)] for j in range(vs)]
            for j in range(vs-1):
                for i in range(us-1):
                    self.face([idx[j][i],idx[j][i+1],idx[j+1][i+1],idx[j+1][i]],finish,s.flip != reverse)
            return [idx[j][i] for i,j in boundary]
        def rim(margin,depth):
            return [vertex(i,j,margin,depth) for i,j in boundary]
        heavy = thickness >= .010
        shoulder = min(.009 if heavy else .0058, min(s.width,s.length)*.085)
        front = grid(shoulder,0,0)
        if self.lod == 0:
            bevel = rim(shoulder*.58,-.0018)
            self.join_rings(front,bevel,2,s.flip)
            outer = rim(0,-thickness*.43)
            self.join_rings(bevel,outer,1 if heavy else 5,s.flip)
            if thickness >= .009:
                backedge = rim(.0004,-thickness*.81)
                self.join_rings(outer,backedge,1,s.flip)
            else:
                backedge = outer
        else:
            if thickness >= .009:
                outer = rim(0,-thickness*.42)
                self.join_rings(front,outer,5,s.flip)
                backedge = outer
            else:
                backedge = front
        back = grid(.0018,-thickness,1,True)
        self.join_rings(backedge,back,1,s.flip)

    def stud(self, u, v, radius):
        p,n = self.sheet.sample(u,v)
        # Each bolt seats on the actual faceted panel, not the smooth interpolant.
        hit,face_normal,_,_ = self.face_bvh.ray_cast(p+n*.016,-n,.040)
        if hit is None or face_normal.dot(n) < .4:
            return
        p,n = hit,face_normal
        x = n.orthogonal().normalized()
        y = n.cross(x)
        def ring(r,z,angle=0):
            return [self.point(p+n*z + r*(x*math.cos(angle+i*math.tau/6)
                                          +y*math.sin(angle+i*math.tau/6))) for i in range(6)]
        outer = ring(radius, .0002)
        bevel = ring(radius*.85, .0016)
        socket = ring(radius*.37, .0016, math.pi/6)
        recess = ring(radius*.31, .00045, math.pi/6)
        self.join_rings(outer,bevel,5,True)
        self.join_rings(bevel,socket,3,True)
        self.join_rings(socket,recess,1,True)
        for k in range(1,5):
            self.face([recess[0],recess[k],recess[k+1]],1)

    def swage(self, path):
        # Beaded pressings stiffen broad faces and catch a narrow directional highlight.
        s = self.sheet
        rows = []
        for u,v,halfwidth,height in path:
            crossbar = []
            for f in (-1.0,-.43,.43,1.0):
                p,n = s.sample(u + halfwidth*f/s.width,v)
                hit,fn,_,_ = self.face_bvh.ray_cast(p+n*.016,-n,.038)
                if hit is None or fn.dot(n)<.35:
                    return
                crossbar.append(hit+fn*(height if abs(f)<.5 else .00015))
            rows.append(crossbar)
        idx = [[self.point(p) for p in row] for row in rows]
        for j in range(len(idx)-1):
            for i in range(3):
                self.face([idx[j][i],idx[j][i+1],idx[j+1][i+1],idx[j+1][i]],4 if i==1 else 5,s.flip)
        for row, rev in ((idx[0],not s.flip),(idx[-1],s.flip)):
            self.face(row,5,rev)

    def cross_pressing(self, abdomen):
        s=self.sheet
        spans=12
        rows=[]
        for i in range(spans+1):
            t=i/spans
            u=.095+.81*t
            span=min(1, min(t,1-t)*12+.14)
            # One folded chevron terminates under the collarbone lugs. The lower
            # breastplate has a shallower transverse return with a broad radius.
            v=(.63-.12*abs(2*t-1)) if abdomen else (.46-.28*abs(2*t-1))
            row=[]
            for dv,lift in ((-.060,.00035),(-.008,.0029),(.017,.0026),(.079,.00035)):
                p,n=s.sample(u,v+dv*span)
                hit,fn,_,_=self.face_bvh.ray_cast(p+n*.020,-n,.045)
                if hit is None or fn.dot(n)<.30:
                    return
                row.append(self.point(hit+fn*(lift*span)))
            rows.append(row)
        for a,b in zip(rows,rows[1:]):
            for j,finish in enumerate((0,2,4)):
                self.face((a[j],b[j],b[j+1],a[j+1]),finish,s.flip)
        self.face(rows[0],5,s.flip)
        self.face(rows[-1],5,not s.flip)

    def mounting_lug(self, a, b, normal):
        # A short solid standoff between the composite backing and the carrier.
        axis = (b-a).normalized()
        x = axis.cross(normal)
        if x.length < .1:
            x = axis.orthogonal()
        x.normalize()
        y = axis.cross(x).normalized()
        def ring(p,w,h):
            return [self.point(p+x*s*w+y*t*h) for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
        start = ring(a,.005,.0023)
        end = ring(b,.005,.0023)
        self.join_rings(start,end,1,True)
        self.face(start,1,True)
        self.face(end,5)

    def hardware(self, name, thickness, carrier, clothing, envelope, bone):
        s = self.sheet
        self.face_bvh = BVHTree.FromPolygons(self.verts,self.faces)
        if not self.lod:
            size=min(s.width,s.length)
            radius=min(.005,max(.0023,size*.049))
            for u,v in ((.16,.2),(.84,.2),(.20,.76),(.80,.76)) if size>.062 else ((.16,.48),(.84,.48)):
                self.stud(u,v,radius)
            if name in ('armorChest','armorAbdomen'):
                self.cross_pressing(name=='armorAbdomen')
            if s.length>.092 and s.width>.068 and name.startswith('armorGreave'):
                tracks = (.27,.73) if s.width>.13 else (.53,)
                for u in tracks:
                    delta=(.5-u)*.4
                    width=min(.0065,s.width*.041)
                    self.swage([(u,.26,width*.25,.0004),
                                (u,.31,width,.0022),(u+delta,.60,width,.0022),
                                (u+delta,.70,width*.28,.0005)])
        self.lugs = 0
        for u in (.12,.88):
            candidates = []
            for v in (.18,.29,.41,.51,.64,.72,.85):
                p,n = s.sample(u,v,-thickness+.001)
                nearby=sorted(carrier.find_nearest_range(p,.041),key=lambda h:h[3])
                for hit,_,_,dist in nearby:
                    if dist>.003 and (hit-p).dot(n)<.0003 and envelope.mounting_clearance(bone,hit):
                        candidates.append((dist,p,n,hit))
                        break
            for dist,p,n,hit in sorted(candidates,key=lambda c:c[0]):
                if all(clothing.find_nearest(p.lerp(hit,t))[3]>.010 for t in (0,.25,.5,.75,1)):
                    self.mounting_lug(p,hit,n)
                    self.lugs += 1
                    break

    def create(self, name, bone, rig, material):
        prefix = "EXO1_" if self.lod else "EXO_"
        name = prefix + name
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.verts,[],self.faces)
        mesh.materials.append(material)
        # Smooth the press-formed skins independently of their machined bevels.
        for poly, finish in zip(mesh.polygons, self.finishes):
            poly.use_smooth = finish == 0
        attr = mesh.attributes.new("armor_finish","INT","FACE")
        attr.data.foreach_set("value",self.finishes)
        mesh.update()
        obj = bpy.data.objects.new(name,mesh)
        bpy.data.collections[f"EXO_LOD{self.lod}"].objects.link(obj)
        obj.parent=rig
        obj.matrix_parent_inverse=rig.matrix_world.inverted()
        obj["t3a_armor"]=True
        obj["frame_standoffs"]=self.lugs
        if self.sheet and any(token in name for token in ('ThighArmor','Pauldron','Vambrace')):
            s=self.sheet
            center=s.sample(.5,.5)[0]
            across=(s.sample(.80,.5)[0]-s.sample(.20,.5)[0]).normalized()
            along=s.sample(.5,.9)[0]-s.sample(.5,.1)[0]
            along=(along-across*along.dot(across)).normalized()
            obj['formed_channel']=[*center,*across,*along,s.width,s.length]
        group=obj.vertex_groups.new(name=bone)
        group.add(list(range(len(mesh.vertices))),1,"REPLACE")
        obj.modifiers.new("EFT Bind Skin","ARMATURE").object=rig
        return obj


class Context:
    def __init__(self):
        from armor_envelope import Envelope
        self.rig = bpy.data.objects['EFT_Bind']
        self.frame = [o for lod in (0,1) for o in bpy.data.collections[f'EXO_LOD{lod}'].objects]
        self.material = bpy.data.materials['exo_mat']
        self.frame_tree = surface_tree(list(bpy.data.collections['EXO_LOD0'].objects))
        self.clothing = surface_tree([bpy.data.objects[n] for n in ('REF_top','REF_pants')])
        self.objects=[]
        self.gorget=[]
        self.flanks={}
        self.envelope=Envelope()
        self.rail_clearance={n:surface_tree([bpy.data.objects[n]]) for n in (
            'EXO_forearmL','EXO_forearmR','EXO_back')}

    def skin(self, origin, direction):
        axis=Vector(direction).normalized()
        hit=self.clothing.ray_cast(Vector(origin)+axis*2,-axis,4)[0]
        if hit is None:
            raise ValueError(f'No clothing along ray at {origin}')
        return hit

    def panel(self,name,bone,rows,thickness=.007,normal=None):
        if bone not in self.rig.data.bones or normal is None:
            raise ValueError((name,bone,normal))
        if not name.lower().startswith('armor'):
            name='armor'+name[:1].upper()+name[1:]
        sheet=Sheet(rows,normal)
        if name.startswith(('armorThigh','armorGreave','armorFauld','armorVambrace')) or name in (
                'armorAbdomen','armorChest','armorBackLumbar','armorFlankRearL','armorFlankRearR'):
            sheet=Sheet(self.envelope.fit(sheet,bone,thickness),normal)
        carrier_name = 'EXO_forearm'+name[-1] if name.startswith('armorVambrace') else 'EXO_back'
        if name.startswith('armorVambrace') or name=='armorBackYoke':
            carrier=self.rail_clearance[carrier_name]
            for j,row in enumerate(sheet.points):
                for i,p in enumerate(row):
                    n=sheet.normals[j][i]
                    gap=carrier.find_nearest(p,.020)
                    if gap[0] is not None:
                        row[i]+=n*(.0055*max(0,1-gap[3]/.020))
            sheet=Sheet(sheet.points,normal)
        if name.startswith('armorGorget'):
            self.gorget.append((sheet,thickness))
        if name in ('armorFlankL','armorFlankR'):
            self.flanks[name[-1]]=(sheet,thickness)
        for lod in (0,1):
            plate=Plate(sheet,lod)
            plate.shell(thickness)
            plate.hardware(name,thickness,self.frame_tree,self.clothing,self.envelope,bone)
            self.objects.append(plate.create(name,bone,self.rig,self.material))

    def carrier(self, name, lod, rings, bone, weights=None, closed=True):
        plate=Plate(None,lod)
        plate.lugs=0
        ring_ids=[[plate.point(v) for v in ring] for ring in rings]
        for index,a in enumerate(ring_ids if closed else ring_ids[:-1]):
            plate.join_rings(a,ring_ids[(index+1)%len(rings)],1)
        if not closed:
            plate.face(ring_ids[0],1)
            plate.face(ring_ids[-1],1,True)
        obj=plate.create(name,bone,self.rig,self.material)
        del obj['t3a_armor']
        obj['t3a_carrier']=True
        if weights:
            obj.vertex_groups.clear()
            for i, influences in enumerate(weights):
                for group_name, weight in influences.items():
                    vg=obj.vertex_groups.get(group_name) or obj.vertex_groups.new(name=group_name)
                    vg.add([i],weight,'REPLACE')
        self.objects.append(obj)

    def suspension(self):
        from fitting import Clothing
        cloth=Clothing()
        for lod in (0,1):
            collar=[]
            for sheet,thickness in self.gorget:
                spans=7 if not lod else 5
                for i in range(spans):
                    collar.append([sheet.sample(i/(spans-1),v,-thickness-d)[0] for v,d in (
                        (.34,-.0002),(.69,-.0002),(.69,.0018),(.34,.0018))])
            self.carrier('gorgetBacking',lod,collar,'Base HumanSpine3')
            rings,weights=[],[]
            segments=22 if not lod else 14
            anchors=[self.flanks[side][0].sample(.54,.55)[0] for side in ('R','L')]
            limits=[math.atan2(p.x,.015-p.y) for p in anchors]
            for i in range(segments+1):
                t=i/segments
                phi=limits[0]*(1-t)+limits[1]*t
                direction=Vector((math.sin(phi),-math.cos(phi),0))
                ring=[]
                for dz,offset in ((-.010,.011),(.010,.011),(.010,.014),(-.010,.014)):
                    center=Vector((0,.015,anchors[0].z*(1-t)+anchors[1].z*t+dz))
                    hit=cloth.tree.ray_cast(center,direction,.34)[0]
                    if hit is None:
                        raise ValueError('No jacket at rib suspension')
                    ring.append(hit+direction*offset)
                    weights.append(cloth.skin(hit))
                rings.append(ring)
            self.carrier('ribSuspension',lod,rings,'Base HumanSpine2',weights,closed=False)


def build():
    if Path(bpy.data.filepath).resolve()!=ROOT/'exo_t3.blend':
        raise ValueError('Open exo_t3.blend as the build input.')
    bpy.context.preferences.filepaths.save_version=0
    bpy.context.preferences.filepaths.file_preview_type='NONE'
    ctx=Context()
    import armor_axial, armor_limbs, armor_atlas
    armor_axial.build(ctx)
    armor_limbs.build(ctx)
    ctx.suspension()
    # Evaluate triangle interiors and garment edges too. The fitting pass
    # moves manufacturing vertices in bind space and preserves rigid weights.
    import clearance
    default_target=clearance.TARGET
    try:
        plates=[obj for obj in ctx.objects if obj.get('t3a_armor')]
        clearance.TARGET=.0061
        for obj in plates:
            ctx.envelope.finish_surface(obj)
        clearance.fit(ctx.objects)
        for obj in plates:
            if 'armorThighArmor' in obj.name:
                ctx.envelope.finish_surface(obj,limit=.02970,max_move=.00165)
            if any(token in obj.name for token in ('ThighArmor','Fauld','Abdomen','Greave','Vambrace','Gorget')):
                ctx.envelope.finish_facets(obj)
        # Nearly opposed standing and crouching clearances at the inner thigh
        # require a final pass on the two skin surfaces of that pressing.
        clearance.TARGET=.00525
        clearance.fit([obj for obj in plates if 'armorThighArmor' in obj.name])
    finally:
        clearance.TARGET=default_target
    armor_atlas.apply(ctx.frame,ctx.objects)
    ctx.rig.data.pose_position='REST'
    bpy.context.scene.render.filepath='//previews_t3a/three_quarter.png'
    for lod,limit in enumerate((30000,10000)):
        total=0
        for obj in bpy.data.collections[f'EXO_LOD{lod}'].objects:
            obj.data.calc_loop_triangles()
            total+=len(obj.data.loop_triangles)
        print(f'LOD{lod}: {total} / {limit}',flush=True)
        if total>limit:
            raise ValueError(f'Over budget: LOD{lod}')
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'exo_t3a.blend'),compress=True)


if __name__=='__main__':
    build()
