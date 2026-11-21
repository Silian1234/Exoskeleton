# Blender (headless): export an exoskeleton tier (collections EXO_LOD0 / EXO_LOD1) to JSON for the Unity build.
# usage: blender -b exo_xx.blend --python export_exo.py -- <out.json>
# Unity mesh space = Blender coords with x negated (verified on FBA); triangle winding reversed; UVs as-is.
import bpy, json, sys
BIND = json.load(open(r"C:\SPT\_fullbody_armor\tools\bindposes.json"))
bind = {}
for m, e in BIND.items():
    for b, v in e["bind"].items(): bind[b] = v

out_path = sys.argv[sys.argv.index("--") + 1]
import numpy as np
used = []
def bone_index(name):
    if name not in bind: raise RuntimeError(f"bone {name} has no EFT bindpose")
    if name not in used: used.append(name)
    return used.index(name)

lods = []
for col in ("EXO_LOD0", "EXO_LOD1"):
    V, N, UV, T, BI, BW = [], [], [], [], [], []
    for o in sorted(bpy.data.collections[col].objects, key=lambda o: o.name):
        if o.type != "MESH": continue
        me = o.data
        me.calc_loop_triangles()
        uvl = me.uv_layers.active.data
        names = {g.index: g.name for g in o.vertex_groups}
        mw = o.matrix_world
        nmat = mw.to_3x3().inverted().transposed()
        corner_normals = me.corner_normals if hasattr(me, "corner_normals") else None
        idx = {}
        for t in me.loop_triangles:
            tri = []
            for k in range(3):
                li = t.loops[k]; vi = me.loops[li].vertex_index
                n = corner_normals[li].vector if corner_normals is not None else me.loops[li].normal
                n = (nmat @ n).normalized()
                uv = tuple(uvl[li].uv)
                key = (vi, round(n.x, 4), round(n.y, 4), round(n.z, 4), round(uv[0], 5), round(uv[1], 5))
                if key not in idx:
                    idx[key] = len(V)
                    co = mw @ me.vertices[vi].co
                    V.append([-co.x, co.y, co.z]); N.append([-n.x, n.y, n.z]); UV.append([uv[0], uv[1]])
                    ws = sorted(((names[g.group], g.weight) for g in me.vertices[vi].groups if g.weight > 1e-5), key=lambda x: -x[1])[:4]
                    s = sum(w for _, w in ws) or 1.0
                    bi = [bone_index(n_) for n_, _ in ws] + [0] * (4 - len(ws))
                    bw = [w / s for _, w in ws] + [0.0] * (4 - len(ws))
                    BI.append(bi); BW.append(bw)
                tri.append(idx[key])
            T.append([tri[0], tri[2], tri[1]])
    lods.append({"v": [c for x in V for c in x], "n": [c for x in N for c in x], "uv": [c for x in UV for c in x],
                 "t": [i for x in T for i in x], "bi": [i for x in BI for i in x], "bw": [w for x in BW for w in x]})
    print(col, "verts", len(V), "tris", len(T))

bones = []
for b in used:
    w = np.array(bind[b]["world"]); bp = np.linalg.inv(w)
    bones.append({"name": b, "path": bind[b]["path"], "bindpose": [float(x) for x in bp.T.flatten()]})
json.dump({"bones": bones, "lods": lods}, open(out_path, "w"))
print("EXPORTED", out_path, "bones", len(bones))
