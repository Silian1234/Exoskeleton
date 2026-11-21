"""Independent read-back checks for skin, rest skeleton, topology, UVs and PNGs."""
from collections import defaultdict
from pathlib import Path
import json
import math
import struct
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parent


def uv_stats(triangles, pairs=None):
    """2D separating-axis test: ignore shared edges but count positive-area overlaps."""
    v = np.asarray(triangles, dtype=np.float64)
    edges = np.roll(v, -1, axis=1) - v
    area = .5 * np.abs(edges[:,0,0]*edges[:,1,1] - edges[:,0,1]*edges[:,1,0])
    v = v[area > 1e-14]
    edges = edges[area > 1e-14]
    axes = np.stack((-edges[:,:,1],edges[:,:,0]),axis=2)
    lengths = np.linalg.norm(axes,axis=2)
    axes /= np.maximum(1e-18,lengths)[:,:,None]
    lo,hi = v.min(axis=1), v.max(axis=1)
    grid = defaultdict(list)
    overlaps = []
    for i in range(len(v)):
        start = np.floor(lo[i]*64).astype(int)
        end = np.floor(hi[i]*64).astype(int)
        cells = [(x,y) for x in range(start[0],end[0]+1) for y in range(start[1],end[1]+1)]
        hits = list({idx for cell in cells for idx in grid[cell]})
        if hits:
            hits = np.asarray(hits)
            hits = hits[np.all((hi[i]>lo[hits]+1e-9) & (hi[hits]>lo[i]+1e-9),axis=1)]
            if len(hits):
                test = np.concatenate((np.broadcast_to(axes[i],(len(hits),3,2)), axes[hits]),axis=1)
                a = np.einsum('nkd,jd->nkj',test,v[i])
                b = np.einsum('nkd,njd->nkj',test,v[hits])
                depth = np.minimum(a.max(2),b.max(2))-np.maximum(a.min(2),b.min(2))
                overlaps.extend((int(j),i) for j in hits[np.all(depth>1e-8,axis=1)])
        for cell in cells:
            grid[cell].append(i)
    if pairs is not None:
        pairs.extend(overlaps)
    return {'triangle_area_percent':round(float(area.sum()*100),3),
            'degenerate_uv_triangles':int((area<=1e-14).sum()), 'positive_overlap_pairs':len(overlaps),
            'outside_unit_square':int(np.any((v<-.000001)|(v>1.000001),axis=(1,2)).sum())}


def audit():
    rig = bpy.data.objects['EFT_Bind']
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    # Read the original rig from the supplied local file for exact comparison.
    with bpy.data.libraries.load(str(ROOT/'base_scene.blend')) as (source, dest):
        dest.objects = ['EFT_Bind']
    original = dest.objects[0]
    check(rig.matrix_world == original.matrix_world, 'Armature object transform')
    check(set(rig.data.bones.keys()) == set(original.data.bones.keys()), 'Bone names')
    for bone in rig.data.bones:
        other = original.data.bones[bone.name]
        check(bone.matrix_local == other.matrix_local and bone.head_local == other.head_local and
              bone.tail_local == other.tail_local and
              (bone.parent.name if bone.parent else None)==(other.parent.name if other.parent else None),
              'Bind mismatch '+bone.name)
    check(rig.data.pose_position=='REST','Armature not saved in REST')
    parts = {}
    uvs = []
    for lod in (0,1):
        prefix = 'EXO_' if lod==0 else 'EXO1_'
        collection = bpy.data.collections['EXO_LOD'+str(lod)]
        count = 0
        for obj in collection.objects:
            name = obj.name
            check(name.startswith(prefix), 'Name '+name)
            check(len(obj.modifiers)==1 and obj.modifiers[0].type=='ARMATURE' and obj.modifiers[0].object==rig,'Armature modifier '+name)
            check([m.name for m in obj.data.materials]==['exo_mat'],'Material '+name)
            check(all(len(p.vertices)<=4 for p in obj.data.polygons),'N-gon '+name)
            check(len(obj.data.uv_layers)==1,'UV layer '+name)
            mesh = obj.data
            mesh.calc_loop_triangles()
            for vertex in mesh.vertices:
                groups = [x for x in vertex.groups if x.weight>0]
                check(1<=len(groups)<=4 and abs(sum(x.weight for x in groups)-1)<1e-5,
                      'Weights '+name)
                check(all(obj.vertex_groups[x.group].name in rig.data.bones for x in groups),'Bone groups '+name)
            uv = mesh.uv_layers.active.data
            for tri in mesh.loop_triangles:
                check(tri.area>1e-12,'Degenerate geometry '+name)
                uvs.append([tuple(uv[i].uv) for i in tri.loops])
            count += len(mesh.loop_triangles)
            parts[name] = [len(mesh.loop_triangles), [g.name for g in obj.vertex_groups]]
        check(count <= (14000,5000)[lod],f'LOD{lod} exceeds budget: {count}')
    atlas = uv_stats(uvs)
    for key in ('degenerate_uv_triangles','positive_overlap_pairs','outside_unit_square'):
        check(atlas[key]==0, key+' '+str(atlas[key]))
    texinfo = {}
    for suffix in ('dif','nrm','gloss'):
        name = 'exo_'+suffix
        file = ROOT/'textures'/(name+'.png')
        with file.open('rb') as f:
            ihdr = f.read(33)
        check(ihdr[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',ihdr[16:24])==(2048,2048),'PNG dimensions '+name)
        image = bpy.data.images[name]
        check(Path(bpy.path.abspath(image.filepath)).resolve()==file,'Image path '+name)
        rgba = np.empty(len(image.pixels),dtype=np.float32)
        image.pixels.foreach_get(rgba)
        rgba = rgba.reshape(-1,4)
        check(np.min(rgba[:,3])>=.9999,'Alpha '+name)
        if suffix == 'gloss':
            check(np.array_equal(rgba[:,0],rgba[:,1]) and np.array_equal(rgba[:,1],rgba[:,2]),'Gloss greyscale')
        texinfo[name] = {'png_bit_depth':ihdr[24],'png_colour_type':ihdr[25],'space':image.colorspace_settings.name}
    result = {'original_bind_bones':len(original.data.bones),'parts':parts,'uv':atlas,'textures':texinfo,'errors':sorted(set(errors))}
    (ROOT/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print('VALIDATION',atlas,result['errors'])
    if result['errors']:
        raise RuntimeError('Model validation failed: '+', '.join(result['errors']))


if __name__=='__main__':
    audit()
