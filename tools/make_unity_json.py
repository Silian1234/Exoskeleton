# plates_export.json (Blender) -> Assets/FBA/plates_unity.json (Unity), with UVs mapped onto the Redut-T5 atlas.
import json, numpy as np

P = json.load(open(r"C:\SPT\_fullbody_armor\tools\plates_export.json"))
BP = json.load(open(r"C:\SPT\_fullbody_armor\tools\bindposes.json"))
TEX = 1024.0
# pixel rects in the Redut dif atlas (x0, x1, y0, y1), y from image top
PANEL = (458, 636, 140, 306)   # camo pad with stitched edge (top-centre panel)
STRAP = (985, 1017, 10, 300)   # tan webbing strip (right edge)


def uv_px(x, y):
    return [x / TEX, 1.0 - y / TEX]


bind = {}
for m, e in BP.items():
    for b, v in e["bind"].items():
        bind[b] = v

out = {"plates": [], "bones": []}
for b in sorted({p["bone"] for p in P["plates"]}):
    w = np.array(bind[b]["world"]); bp = np.linalg.inv(w)
    out["bones"].append({"name": b, "path": bind[b]["path"], "bindpose": [float(x) for x in bp.T.flatten()]})

for p in P["plates"]:
    strap = "_strap" in p["name"]
    uvs = []
    for u, v in p["uvs"]:
        if strap:
            u0 = (u - 0.82) / 0.16            # around the limb
            v0 = v                             # across strap width
            x = STRAP[0] + (STRAP[1] - STRAP[0]) * v0
            y = STRAP[2] + (STRAP[3] - STRAP[2]) * u0
        else:
            u0 = (u - 0.02) / 0.74             # across the arc
            v0 = (v - 0.02) / 0.96             # along the limb, 0 = upper end
            x = PANEL[0] + (PANEL[1] - PANEL[0]) * u0
            y = PANEL[2] + (PANEL[3] - PANEL[2]) * v0
        uvs += uv_px(x, y)
    out["plates"].append({"name": p["name"], "bone": p["bone"],
                          "v": [c for x in p["verts"] for c in x], "n": [c for x in p["normals"] for c in x],
                          "uv": uvs, "t": [i for x in p["tris"] for i in x]})
json.dump(out, open(r"C:\SPT\_fullbody_armor\unity\FBA\Assets\FBA\plates_unity.json", "w"))
print("ok", len(out["plates"]))
