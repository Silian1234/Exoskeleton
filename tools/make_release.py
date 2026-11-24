# Builds dist/FullBodyArmor-<version>-SPT-4.1.6.zip from the current build outputs.
# Layout matches the 1.1.0 release: server mod under SPT_Runtime/user/mods/FullBodyArmor, client under BepInEx/plugins.
# Run: python tools/make_release.py [version]
import os, sys, zipfile

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = sys.argv[1] if len(sys.argv) > 1 else "1.1.1"
OUT = os.path.join(R, "dist", f"FullBodyArmor-{VERSION}-SPT-4.1.6.zip")
S = "SPT_Runtime/user/mods/FullBodyArmor/"
C = "BepInEx/plugins/FullBodyArmorClient/"
INSTALLED = r"C:\SPT41\SPT_Runtime\user\mods\FullBodyArmor"   # bundles live only in the installed mod


def p(*parts):
    return os.path.join(R, *parts)


files = {
    S + "FullBodyArmor.dll": p("server", "bin", "Release", "net10.0", "FullBodyArmor.dll"),
    S + "locales.json": p("server", "locales.json"),
    C + "FullBodyArmorClient.dll": p("client", "bin", "Release", "FullBodyArmorClient.dll"),
}
# files kept from the previous release (unchanged since 1.1.0)
prev = os.path.join(R, "dist", "FullBodyArmor-1.1.0-SPT-4.1.6.zip")
with zipfile.ZipFile(prev) as z:
    kept = {n: z.read(n) for n in z.namelist() if n not in files and not n.endswith("/")}

missing = [src for src in files.values() if not os.path.isfile(src)]
if missing:
    sys.exit("missing: " + ", ".join(missing))
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for arc, data in sorted(kept.items()):
        z.writestr(arc, data)
    for arc, src in sorted(files.items()):
        z.write(src, arc)
print(f"{len(kept) + len(files)} files ({len(files)} updated), {os.path.getsize(OUT) / 1e6:.1f} MB -> {OUT}")
