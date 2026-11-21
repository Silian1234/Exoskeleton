"""Shared world-space mesh builder for the original EXO-3 assemblies."""
import math
import bmesh
import bpy
from mathutils import Matrix, Vector


class Geometry:
    def __init__(self, lod, rig, materials):
        self.lod = lod
        self.rig = rig
        self.materials = materials
        self.parts = {}
        self.collection = bpy.data.collections.new(f'EXO_LOD{lod}')
        bpy.context.scene.collection.children.link(self.collection)
        self.current = None

    def head(self, bone):
        return self.rig.matrix_world @ self.rig.data.bones[bone].head_local

    def part(self, name, bone):
        if bone not in self.rig.data.bones:
            raise KeyError(bone)
        self.current = self.parts.setdefault(name, ([], [], [], {}))
        self.current_bone = bone

    def mesh(self, verts, faces, style=0, weights=None):
        points, polys, styles, groups = self.current
        offset = len(points)
        points.extend(tuple(p) for p in verts)
        if weights is None:
            groups.setdefault((self.current_bone,1.0), []).extend(range(offset, len(points)))
        else:
            if len(weights) != len(points)-offset:
                raise ValueError('Expected a weight dictionary per vertex')
            for index, influences in enumerate(weights, offset):
                assert abs(sum(influences.values())-1) < 1e-6
                for bone, weight in influences.items():
                    if weight:
                        groups.setdefault((bone,weight),[]).append(index)
        polys.extend(tuple(offset + i for i in f) for f in faces)
        styles.extend([style] * len(faces) if isinstance(style, int) else style)

    def tube(self, points, r, style=0, n=6, end_radius=None, bones=None):
        points = [Vector(p) for p in points]
        rings = []
        axis_u = None
        for i, point in enumerate(points):
            axis = (points[min(i+1, len(points)-1)] - points[max(0, i-1)]).normalized()
            if axis_u is None:
                axis_u = axis.orthogonal().normalized()
            else:
                axis_u = (axis_u - axis * axis.dot(axis_u)).normalized()
            axis_v = axis.cross(axis_u)
            radius = r if end_radius is None else r + (end_radius-r)*i/(len(points)-1)
            for k in range(n):
                angle = math.tau * k / n
                rings.append(point + radius*(math.cos(angle)*axis_u + math.sin(angle)*axis_v))
        faces = [tuple(reversed(range(n)))]
        for i in range(len(points)-1):
            base = n*i
            faces.extend((base+k, base+(k+1)%n, base+n+(k+1)%n, base+n+k) for k in range(n))
        faces.append(tuple(range(len(rings)-n,len(rings))))
        weights = None
        if bones:
            weights = []
            for i in range(len(points)):
                t = i/(len(points)-1)
                weights.extend([{bones[0]:1-t,bones[1]:t} for _ in range(n)])
        self.mesh(rings,faces,style,weights=weights)

    def rod(self, a, b, r, style=0, n=8, r2=None):
        self.tube([a,b],r,style,n,end_radius=r2)

    def box(self, center, size, style=0, bevel=0, quat=None):
        center, size = Vector(center), Vector(size)
        rot = quat.to_matrix() if quat is not None else Matrix.Identity(3)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts:
            v.co = Vector([v.co[i]*size[i] for i in range(3)])
        if bevel > 0 and self.lod == 0:
            bmesh.ops.bevel(bm,geom=bm.edges[:],offset=min(bevel,min(size)*.42),
                            segments=1,affect='EDGES')
        bm.verts.index_update()
        self.mesh([center + rot @ v.co for v in bm.verts],
                  [tuple(v.index for v in f.verts) for f in bm.faces],style)
        bm.free()

    def beam(self, a, b, width, depth, style=0, bevel=0, ref=(1,0,0)):
        a,b = Vector(a),Vector(b)
        axis = (b-a).normalized()
        right = Vector(ref) - axis * axis.dot(Vector(ref))
        if right.length < .0001:
            right = axis.orthogonal()
        right.normalize()
        rot = Matrix((right, axis.cross(right), axis)).transposed().to_quaternion()
        self.box((a+b)*.5,(width,depth,(b-a).length),style,bevel,rot)

    def finish(self):
        objects = []
        for part, (verts, faces, styles, groups) in self.parts.items():
            name = ('EXO_' if self.lod == 0 else 'EXO1_') + part
            data = bpy.data.meshes.new(name)
            data.from_pydata(verts, [], faces)
            for mat in self.materials:
                data.materials.append(mat)
            data.polygons.foreach_set('material_index', styles)
            obj = bpy.data.objects.new(name,data)
            self.collection.objects.link(obj)
            for (bone,weight),indices in groups.items():
                group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
                group.add(indices,weight,'REPLACE')
            bm = bmesh.new()
            bm.from_mesh(data)
            loose = [v for v in bm.verts if not v.link_faces]
            if loose:
                bmesh.ops.delete(bm,geom=loose,context='VERTS')
            bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:])
            large = [f for f in bm.faces if len(f.verts)>4]
            if large:
                bmesh.ops.triangulate(bm,faces=large)
            bm.to_mesh(data)
            bm.free()
            data.update()
            obj.parent = self.rig
            deform = obj.modifiers.new('EFT Bind Skin','ARMATURE')
            deform.object = self.rig
            objects.append(obj)
        return objects
