# Re-point external references of an UNCOMPRESSED Unity-built bundle from our placeholder bundles
# (shaders / cubemaps / physicsmaterials built in our project) to the game's real bundles.
# Patching is done in place on bytes: CAB names have equal length, pathIDs are int64.
import struct, sys, shutil
import unityfs as U

GAME = r"C:\SPT\EscapeFromTarkov_Data\StreamingAssets\Windows"
BUILD = r"C:\SPT\_fullbody_armor\unity\build"
SRC = BUILD + r"\assets\content\items\equipment\fba\item_equipment_fba_carrier.bundle"
DST = sys.argv[1] if len(sys.argv) > 1 else SRC.replace(".bundle", ".patched.bundle")

# Targets taken from the game's Redut-T5 bundle (its material and loot colliders).
GAME_SHADERS_CAB = "CAB-56d919bd5479d38f741da52a6beef92f"
GAME_CUBEMAPS_CAB = "CAB-4d8a4131cf377709ee7c7e960f65d349"
GAME_PHYS_CAB = "CAB-c4ae8b769ad32b6f6553d77ccc5aff87"
GAME_SHADER_PID = 5560642222599436764
GAME_CUBE_PID = 972550011776207695


def placeholder(path, classid):
    meta, files = U.read_bundle(path)
    cab = [n for n, _ in meta['nodes'] if not n.endswith('.resS')][0]
    sf = U.SF(files[cab])
    pids = [o['pathID'] for o in sf.objects if o['classID'] == classid]
    assert len(pids) == 1, (path, pids)
    return cab, pids[0]


def game_phys_pid():
    meta, files = U.read_bundle(GAME + r"\assets\content\items\equipment\armor_redut_t5\item_equipment_armor_redut_t5.bundle")
    sf = U.SF(files[[n for n, _ in meta['nodes'] if not n.endswith('.resS')][0]])
    ext = sf.externals
    found = set()
    for o in sf.objects:
        if o['classID'] == 65:  # BoxCollider: m_GameObject PPtr(12) then m_Material PPtr
            d = sf.obj_bytes(o)
            fid, pid = struct.unpack('<iq', d[12:24])
            found.add((ext[fid - 1] if fid > 0 else None, pid))
    assert len(found) == 1, found
    (cabpath, pid), = found
    assert GAME_PHYS_CAB in cabpath, cabpath
    return pid


our_sh_cab, our_sh_pid = placeholder(BUILD + r"\shaders", 48)
our_cu_cab, our_cu_pid = placeholder(BUILD + r"\cubemaps", 89)
our_ph_cab, our_ph_pid = placeholder(BUILD + r"\assets\commonassets\physics\physicsmaterials.bundle", 134)
GAME_PHYS_PID = game_phys_pid()
print("ours:", our_sh_cab, our_sh_pid, our_cu_cab, our_cu_pid, our_ph_cab, our_ph_pid)
print("game phys pid:", GAME_PHYS_PID)

b = bytearray(open(SRC, 'rb').read())


def rep(old, new, expect_min=1):
    assert len(old) == len(new)
    n = b.count(old)
    assert n >= expect_min, (old, n)
    i = 0
    while True:
        i = b.find(old, i)
        if i < 0: break
        b[i:i + len(old)] = new; i += len(new)
    return n


print("shaders CAB", rep(our_sh_cab.encode(), GAME_SHADERS_CAB.encode()))
print("cubemaps CAB", rep(our_cu_cab.encode(), GAME_CUBEMAPS_CAB.encode()))
print("phys CAB", rep(our_ph_cab.encode(), GAME_PHYS_CAB.encode()))
print("shader pid", rep(struct.pack('<q', our_sh_pid), struct.pack('<q', GAME_SHADER_PID)))
print("cube pid", rep(struct.pack('<q', our_cu_pid), struct.pack('<q', GAME_CUBE_PID)))
print("phys pid", rep(struct.pack('<q', our_ph_pid), struct.pack('<q', GAME_PHYS_PID)))
open(DST, 'wb').write(b)

# verify
meta, files = U.read_bundle(DST)
cab = [n for n, _ in meta['nodes'] if not n.endswith('.resS')][0]
sf = U.SF(files[cab])
print("externals:", sf.externals)
for o in sf.objects:
    if o['classID'] == 21: print("material", U.material_pptrs(sf, o))
print("written", DST)
