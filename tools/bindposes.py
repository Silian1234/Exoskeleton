# Extract bone bind poses (bone world matrices in mesh space) from AssetRipper Unity export.
# For each prefab with EFT Skin components: SkinnedMeshRenderer -> mesh asset -> m_BindPose, paired with _bonePaths.
import json, re, sys, os, glob
import numpy as np

ROOT = r"C:\SPT\_fullbody_armor\rip_unity\ExportedProject\Assets"
OUT = r"C:\SPT\_fullbody_armor\tools\bindposes.json"

guid2file = {}
for meta in glob.glob(os.path.join(ROOT, "Mesh", "*.asset.meta")):
    g = re.search(r"guid: (\w+)", open(meta, encoding="utf-8").read()).group(1)
    guid2file[g] = meta[:-5]

def docs(text):
    parts = re.split(r"^--- !u!(\d+) &(\d+).*$", text, flags=re.M)
    out = {}
    for i in range(1, len(parts), 3):
        out[parts[i + 1]] = (parts[i], parts[i + 2])
    return out

def bindposes(meshfile):
    t = open(meshfile, encoding="utf-8").read()
    sec = t.split("m_BindPose:")[1].split("m_BoneNameHashes")[0]
    mats = []
    for block in sec.split("- e00:")[1:]:
        vals = {"e00": float(block.split("\n")[0])}
        for k, v in re.findall(r"(e\d\d): ([-\dE.+]+)", block):
            vals[k] = float(v)
        m = np.array([[vals[f"e{r}{c}"] for c in range(4)] for r in range(4)])
        mats.append(m)
    return mats

result = {}
for prefab in glob.glob(os.path.join(ROOT, "Content", "**", "*.prefab"), recursive=True):
    d = docs(open(prefab, encoding="utf-8").read())
    for fid, (cls, body) in d.items():
        if cls != "114" or "_bonePaths" not in body:
            continue
        smr = re.search(r"_skinnedMeshRenderer: \{fileID: (\d+)\}", body).group(1)
        paths = re.findall(r"^  - (Root_Joint.*)$", body, flags=re.M)
        mg = re.search(r"m_Mesh: \{fileID: \d+, guid: (\w+)", d[smr][1]).group(1)
        mf = guid2file[mg]
        bps = bindposes(mf)
        assert len(bps) == len(paths), (mf, len(bps), len(paths))
        meshname = os.path.basename(mf)[:-6]
        entry = {}
        for p, bp in zip(paths, bps):
            w = np.linalg.inv(bp)  # bone-to-mesh matrix
            entry[p.split("/")[-1]] = {"path": p, "world": w.tolist()}
        result[meshname] = {"prefab": os.path.basename(prefab), "bones": [p.split("/")[-1] for p in paths], "bind": entry}
        print(meshname, len(paths))

json.dump(result, open(OUT, "w"), indent=1)
# consistency: same bone across meshes should share bind pose
allb = {}
for m, e in result.items():
    for b, v in e["bind"].items():
        allb.setdefault(b, []).append((m, np.array(v["world"])))
for b, lst in sorted(allb.items()):
    base = lst[0][1]
    dev = max(np.abs(x[1] - base).max() for x in lst)
    print(f"{b:28s} n={len(lst)} maxdev={dev:.4f} pos={np.round(base[:3,3],3)}")
