# Independent check of GPT's exo_model.blend (run in background Blender).
import bpy, json, collections
out = {}
arm = bpy.data.objects.get("EFT_Bind")
bones = set(b.name for b in arm.data.bones)
for col in ("EXO_LOD0", "EXO_LOD1"):
    c = bpy.data.collections[col]
    tris = 0; parts = {}
    for o in c.objects:
        if o.type != "MESH": continue
        me = o.data
        me.calc_loop_triangles()
        tris += len(me.loop_triangles)
        names = {g.index: g.name for g in o.vertex_groups}
        bad = sorted(set(names.values()) - bones)
        per_bone = collections.Counter(); maxinf = 0; badsum = 0
        for v in me.vertices:
            ws = [(names[g.group], g.weight) for g in v.groups if g.weight > 1e-4]
            maxinf = max(maxinf, len(ws))
            s = sum(w for _, w in ws)
            if abs(s - 1) > 0.01: badsum += 1
            for n, w in ws: per_bone[n] += w
        tot = sum(per_bone.values()) or 1
        side = "L" if o.name.endswith("L") else ("R" if o.name.endswith("R") else "")
        cross = sum(w for n, w in per_bone.items() if side and (("HumanR" in n) if side == "L" else ("HumanL" in n))) / tot
        parts[o.name] = dict(tris=len(me.loop_triangles), verts=len(me.vertices), unknown_groups=bad, max_influences=maxinf,
                             unnormalized=badsum, cross_side_share=round(cross, 4),
                             top=[(n, round(w / tot, 3)) for n, w in per_bone.most_common(4)],
                             mods=[m.type for m in o.modifiers], mats=[m.name for m in me.materials if m],
                             uv=len(me.uv_layers))
    out[col] = dict(tris=tris, parts=parts)
print("EXOCHECK" + json.dumps(out))
