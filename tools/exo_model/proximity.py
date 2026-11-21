"""Closest features of two disjoint triangular surfaces within a search radius."""
from itertools import product
from collections import defaultdict
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def edges_of(triangles):
    return np.asarray(sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)}))


def cells(lo,hi):
    return product(range(lo[0],hi[0]+1),range(lo[1],hi[1]+1),range(lo[2],hi[2]+1))


class Garment:
    def __init__(self,points,triangles):
        self.pts=np.asarray(points)
        self.triangles=triangles
        self.tree=BVHTree.FromPolygons(points,triangles,all_triangles=True)
        edges=edges_of(triangles)
        # The imported body contains coincident vertices at UV seams.
        segments=np.sort(edges,axis=1)
        self.a=self.pts[segments[:,0]]
        self.b=self.pts[segments[:,1]]
        self.lo=np.minimum(self.a,self.b)
        self.hi=np.maximum(self.a,self.b)
        self.grid=defaultdict(list)
        for i,(lo,hi) in enumerate(zip(np.floor(self.lo/.045).astype(int),np.floor(self.hi/.045).astype(int))):
            for key in cells(lo,hi):
                self.grid[key].append(i)


class Pair:
    def __init__(self,garment,points,triangles,reach):
        self.garment=garment
        self.triangles=np.asarray(triangles)
        self.edges=edges_of(triangles)
        self.reach=reach
        self.forward=[i for i,p in enumerate(points) if garment.tree.find_nearest(Vector(p),reach)[0] is not None]
        lo=points.min(0)-reach
        hi=points.max(0)+reach
        ids=np.flatnonzero(np.all((garment.pts>=lo)&(garment.pts<=hi),axis=1))
        exo=BVHTree.FromPolygons(points,triangles,all_triangles=True)
        self.reverse=[i for i in ids if exo.find_nearest(Vector(garment.pts[i]),reach)[0] is not None]
        a=points[self.edges[:,0]]; b=points[self.edges[:,1]]
        lows=np.minimum(a,b)-reach; highs=np.maximum(a,b)+reach
        refs=[]; model=[]
        for i,(clo,chi) in enumerate(zip(np.floor(lows/.045).astype(int),np.floor(highs/.045).astype(int))):
            hits=list({k for cell in cells(clo,chi) for k in garment.grid.get(cell,())})
            if not hits: continue
            good=np.all((garment.hi[hits]>=lows[i])&(garment.lo[hits]<=highs[i]),axis=1)
            qualified=np.asarray(hits)[good]
            refs.extend(qualified); model.extend([i]*len(qualified))
        self.refs=np.asarray(refs,dtype=int)
        self.model=np.asarray(model,dtype=int)

    def features(self,points,limit):
        """Yield separation vectors from garment to model and the supporting model vertices."""
        g=self.garment
        for i in self.forward:
            p=points[i]
            hit,_,_,d=g.tree.find_nearest(Vector(p),limit)
            if hit is not None:
                yield (i,),p-np.asarray(hit),d
        if self.reverse:
            exo=BVHTree.FromPolygons(points,self.triangles,all_triangles=True)
            for i in self.reverse:
                p=g.pts[i]
                hit,_,idx,d=exo.find_nearest(Vector(p),limit)
                if hit is not None:
                    yield self.triangles[idx],np.asarray(hit)-p,d
        if not len(self.model):return
        ids=self.edges[self.model]
        a=points[ids[:,0]]; u=points[ids[:,1]]-a
        c=g.a[self.refs]; v=g.b[self.refs]-c
        w=a-c
        dot=lambda x,y:np.einsum('ij,ij->i',x,y)
        uu=dot(u,u); vv=dot(v,v); uv=dot(u,v); uw=dot(u,w); vw=dot(v,w)
        det=uu*vv-uv*uv
        safe=np.where(det>1e-18,det,1)
        t=(uv*vw-vv*uw)/safe; s=(uu*vw-uv*uw)/safe
        inside=(det>1e-18)&(t>0)&(t<1)&(s>0)&(s<1)
        delta=w+t[:,None]*u-s[:,None]*v
        d2=dot(delta,delta)
        for i in np.flatnonzero(inside & (d2<limit**2)):
            yield ids[i],delta[i],np.sqrt(d2[i])
