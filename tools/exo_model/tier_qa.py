"""Read-only audit: blender -b exo_t2.blend --python tier_qa.py -- 2."""
from pathlib import Path
import sys, json, struct
import bpy
import numpy as np
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import review
from validate import uv_stats

def main():
    tier = int(sys.argv[sys.argv.index('--') + 1])
    assert tier in (2,3)
    assert Path(bpy.data.filepath).resolve() == ROOT / f'exo_t{tier}.blend'
    errors=[]
    def check(ok, msg):
        if not ok: errors.append(msg)
    rig=bpy.data.objects['EFT_Bind']
    with bpy.data.libraries.load(str(ROOT/'base_scene.blend')) as (source, dest):
        dest.objects=['EFT_Bind']
    original=dest.objects[0]
    check(rig.matrix_world == original.matrix_world,'armature world transform')
    check(set(rig.data.bones.keys()) == set(original.data.bones.keys()),'bone names')
    for b in rig.data.bones:
        other=original.data.bones.get(b.name)
        check(other is not None and b.matrix_local == other.matrix_local and b.head_local == other.head_local and b.tail_local == other.tail_local and (b.parent.name if b.parent else None)==(other.parent.name if other.parent else None),'bind mismatch '+b.name)
    check(rig.data.pose_position == 'REST','not saved in REST')
    parts={}; atlases={}; totals={}; combined_uv=[]
    for lod in (0,1):
        prefix=('EXO_' if lod==0 else 'EXO1_')
        collection=bpy.data.collections.get('EXO_LOD'+str(lod))
        check(collection is not None,'missing LOD collection '+str(lod))
        triangles=[]; total=0
        if collection is None: continue
        for obj in collection.objects:
            check(obj.type=='MESH','non-mesh '+obj.name)
            if obj.type!='MESH': continue
            check(obj.name.startswith(prefix),'name '+obj.name)
            check(len(obj.modifiers)==1 and obj.modifiers[0].type=='ARMATURE' and obj.modifiers[0].object==rig,'armature modifier '+obj.name)
            check([m.name if m else None for m in obj.data.materials]==['exo_mat'],'material '+obj.name)
            check(all(len(p.vertices)<=4 for p in obj.data.polygons),'ngons '+obj.name)
            check(len(obj.data.uv_layers)==1,'UV layer '+obj.name)
            mesh=obj.data; mesh.calc_loop_triangles()
            used=set()
            for v in mesh.vertices:
                groups=[g for g in v.groups if g.weight>0]
                check(1<=len(groups)<=4 and abs(sum(g.weight for g in groups)-1)<1e-5,'weights '+obj.name)
                for g in groups:
                    name=obj.vertex_groups[g.group].name
                    used.add(name); check(name in rig.data.bones,'unknown bone '+obj.name+': '+name)
            if mesh.uv_layers.active:
                uv=mesh.uv_layers.active.data
                for tri in mesh.loop_triangles:
                    check(tri.area>1e-12,'degenerate geometry '+obj.name)
                    triangles.append([tuple(uv[i].uv) for i in tri.loops])
            total+=len(mesh.loop_triangles)
            parts[obj.name]={'triangles':len(mesh.loop_triangles),'bones':sorted(used)}
        totals['LOD'+str(lod)]=total
        check(total <= ({2:(18000,6500),3:(22000,8000)}[tier][lod]),'triangle budget LOD'+str(lod))
        combined_uv.extend(triangles)
        atlases['LOD'+str(lod)]=uv_stats(triangles) if triangles else {}
        for key in ('degenerate_uv_triangles','positive_overlap_pairs','outside_unit_square'):
            check(atlases['LOD'+str(lod)].get(key)==0,'LOD'+str(lod)+' UV '+key)
    atlases['combined']=uv_stats(combined_uv) if combined_uv else {}
    for key in ('degenerate_uv_triangles','positive_overlap_pairs','outside_unit_square'):
        check(atlases['combined'].get(key)==0,'combined UV '+key)
    mat=bpy.data.materials.get('exo_mat')
    material_images={}
    if not mat or not mat.use_nodes:
        errors.append('missing node material exo_mat')
    else:
        for node in mat.node_tree.nodes:
            if node.type=='TEX_IMAGE' and node.image:
                image=node.image; name=image.name
                material_images[name]={'path':image.filepath,'colorspace':image.colorspace_settings.name}
                expected=ROOT/f'textures_t{tier}'/(name+'.png')
                check(image.filepath.startswith('//') and Path(bpy.path.abspath(image.filepath)).resolve()==expected,'texture node path '+name)
                check(image.colorspace_settings.name==('sRGB' if name=='exo_dif' else 'Non-Color'),'texture node colorspace '+name)
        for name in ('exo_dif','exo_nrm','exo_gloss'):
            check(name in material_images,'missing texture node '+name)
    textures={}
    for suffix in ('dif','nrm','gloss'):
        path=ROOT/f'textures_t{tier}'/f'exo_{suffix}.png'
        if not path.exists(): errors.append('missing texture '+str(path)); continue
        head=path.read_bytes()[:33]
        check(head[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',head[16:24])==(2048,2048),'PNG dimensions '+suffix)
        img=bpy.data.images.load(str(path),check_existing=True)
        rgba=np.empty(len(img.pixels),dtype=np.float32); img.pixels.foreach_get(rgba); rgba=rgba.reshape(-1,4)
        check(np.min(rgba[:,3])>=.9999,'alpha '+suffix)
        if suffix=='gloss': check(np.array_equal(rgba[:,0],rgba[:,1]) and np.array_equal(rgba[:,1],rgba[:,2]),'gloss not grayscale')
        textures[suffix]={'path':str(path),'bit_depth':head[24],'color_type':head[25],'alpha_min':float(rgba[:,3].min()),'colorspace':img.colorspace_settings.name}
    measurements={}
    layer=bpy.context.view_layer.layer_collection.children.get('EXO_LOD1')
    layer_hidden=layer.hide_viewport if layer else None
    collection=bpy.data.collections.get('EXO_LOD1')
    collection_hidden=collection.hide_viewport if collection else None
    if layer: layer.hide_viewport=False
    if collection: collection.hide_viewport=False
    hidden={o.name:(o.hide_viewport,o.hide_get()) for o in bpy.data.objects if o.name.startswith(('EXO_','EXO1_'))}
    for name in hidden:
        o=bpy.data.objects[name]; o.hide_viewport=False; o.hide_set(False)
    bpy.context.view_layer.update()
    try:
        for name in review.POSES:
            review.set_pose(name)
            measurements[name]=review.measure()
            print('TIER QA',tier,name,flush=True)
    finally:
        review.restore_pose()
        for name,(viewport,hidden_set) in hidden.items():
            o=bpy.data.objects[name]; o.hide_viewport=viewport; o.hide_set(hidden_set)
        if layer: layer.hide_viewport=layer_hidden
        if collection: collection.hide_viewport=collection_hidden
    result={'tier':tier,'blend':bpy.data.filepath,'bind_bones':len(original.data.bones),'triangles':totals,'parts':parts,'uv':atlases,'textures':textures,'material_images':material_images,'errors':sorted(set(errors)),'poses':measurements,'caveat':'Surface intersection pairs indicate triangle crossings. Open clothing does not define reliable inside; no crossings do not prove no penetration. Closest gaps search only to 26 mm; null means no pair within search radius.'}
    (ROOT/f'tier_qa_t{tier}.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print('STRUCTURAL ERRORS',result['errors'],flush=True)
if __name__=='__main__': main()
