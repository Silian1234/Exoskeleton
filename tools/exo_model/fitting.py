"""Sample a garment surface and interpolate the bind weights at a surface hit."""
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


class Clothing:
    def __init__(self):
        self.triangles = []
        self.vertices = []
        self.weights = []
        for name in ('REF_pants','REF_top'):
            obj = bpy.data.objects[name]
            mesh = obj.data
            mesh.calc_loop_triangles()
            offset = len(self.vertices)
            self.vertices.extend(obj.matrix_world @ v.co for v in mesh.vertices)
            self.weights.extend({obj.vertex_groups[g.group].name:g.weight for g in v.groups if g.weight>0}
                                for v in mesh.vertices)
            self.triangles.extend(tuple(offset+i for i in tri.vertices) for tri in mesh.loop_triangles)
        self.tree = BVHTree.FromPolygons(self.vertices,self.triangles,all_triangles=True)

    def skin(self, point):
        surface, normal, index, dist = self.tree.find_nearest(Vector(point))
        ia,ib,ic = self.triangles[index]
        a,b,c = [self.vertices[i] for i in (ia,ib,ic)]
        ab,ac,ap = b-a,c-a,surface-a
        normal = ab.cross(ac)
        det = normal.length_squared
        if det < 1e-20:
            wb=wc=0
        else:
            wb=ap.cross(ac).dot(normal)/det
            wc=ab.cross(ap).dot(normal)/det
        combined = {}
        for i,influence in ((ia,1-wb-wc),(ib,wb),(ic,wc)):
            for name,weight in self.weights[i].items():
                combined[name] = combined.get(name,0)+max(influence,0)*weight
        best = sorted(combined.items(),key=lambda pair:-pair[1])[:4]
        total = sum(v for _,v in best)
        return {n:v/total for n,v in best if v>0}
