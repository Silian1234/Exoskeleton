# Generates server/config/weapons.json: one best-stat build per popular weapon, vanilla items only.
# Score per attachment: lower recoil first, then ergonomics; a red dot / holo sight gets a bonus so every build
# has an optic. Magazines: the largest vanilla magazine. Ammo: the highest-penetration vanilla round the magazine takes.
# Usage: python make_vanilla_builds.py <SPT server folder> <output weapons.json>
import json, os, random, sys

SPT = sys.argv[1] if len(sys.argv) > 1 else r"C:\SPT\SPT"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "server", "config", "weapons.json")
DB = os.path.join(SPT, "SPT_Data", "database")
items = json.load(open(os.path.join(DB, "templates", "items.json"), encoding="utf-8"))
en = json.load(open(os.path.join(DB, "locales", "global", "en.json"), encoding="utf-8"))

WEAPONS = [
    ("5447a9cd4bdc2dbd208b4567", "M4A1"), ("5bb2475ed4351e00853264e3", "HK416A5"),
    ("606587252535c57a13424cfd", "Mk47 Mutant"), ("5ac4cd105acfc40016339859", "AK-74M"),
    ("59d6088586f774275f37482f", "AKM"), ("5ac66d2e5acfc43b321d4b53", "AK-103"),
    ("6499849fc93611967b034949", "AK-12"), ("5fb64bc92b1b027b1f50bcf2", "Vector .45"),
    ("5fc3f2d5900b1d5091531e57", "Vector 9x19"), ("6183afd850224f204c1da514", "SCAR-H"),
    ("65290f395ae2ae97b80fdf2d", "MCX-SPEAR"), ("5beed0f50db834001c062b12", "RPK-16"),
]
AMMO, MAG = "5485a8684bdc2da71d8b4567", "5448bc234bdc2d3c308b4569"
SIGHTS = {"55818ad54bdc2ddc698b4569", "55818acf4bdc2dde698b456b"}       # collimator, compact collimator
NO_SCOPES = {"55818ae44bdc2dde698b456c", "55818aeb4bdc2ddc698b456a", "55818add4bdc2d5b648b456f"}  # optic, special, assault scope
SKIP_SLOTS = {"mod_magazine", "patron_in_weapon", "cartridges"}
MAX_DEPTH = 9

name = lambda t: en.get(t + " Name") or items[t]["_name"]


def parents(t):
    out = []
    while t in items:
        out.append(t); t = items[t]["_parent"]
    return out


def own_score(t):
    p = items[t]["_props"]
    s = -float(p.get("Recoil", 0) or 0) + 0.6 * float(p.get("Ergonomics", 0) or 0)
    if SIGHTS & set(parents(t)): s += 8
    return s


def usable(t):
    if t not in items or items[t]["_type"] != "Item": return False
    ps = set(parents(t))
    if NO_SCOPES & ps or MAG in ps or AMMO in ps: return False
    return not items[t]["_props"].get("QuestItem")


def best(t, banned, depth=0, memo=None):
    """(score, [(slot, child_tpl, child_tree)]) of the best subtree under t."""
    memo = {} if memo is None else memo
    key = (t, depth)
    if key in memo: return memo[key]
    score, tree = (own_score(t) if depth else 0.0), []
    if depth < MAX_DEPTH:
        for slot in items[t]["_props"].get("Slots", []):
            if slot["_name"] in SKIP_SLOTS: continue
            flt = slot["_props"]["filters"][0].get("Filter", []) if slot["_props"].get("filters") else []
            opts = []
            for c in flt:
                if c in banned or not usable(c): continue
                cs, ct = best(c, banned, depth + 1, memo)
                opts.append((cs, c, ct))
            if not opts: continue
            pick = max(opts, key=lambda o: o[0])
            if slot.get("_required") or pick[0] > 0:
                score += pick[0]; tree.append((slot["_name"], pick[1], pick[2], bool(slot.get("_required"))))
    memo[key] = (score, tree)
    return memo[key]


def flatten(tree, out):
    for slot, c, ct, req in tree:
        out.append(c); flatten(ct, out)
    return out


def is_sight(t): return bool(SIGHTS & set(parents(t)))


def one_sight(tree):
    """Keep the shallowest sight, drop the other sights, then drop optional parts left with no stats and no children."""
    found = []
    def walk(tr, d):
        for e in tr:
            if is_sight(e[1]): found.append((d, len(found), e))
            walk(e[2], d + 1)
    walk(tree, 0)
    keep = min(found, key=lambda f: (f[0], f[1]))[2] if found else None

    def prune(tr):
        out = []
        for e in tr:
            slot, c, ct, req = e
            if is_sight(c):
                if e is keep or req: out.append((slot, c, prune(ct), req))
                continue
            kids = prune(ct)
            if not req and not kids and own_score(c) <= 0: continue
            out.append((slot, c, kids, req))
        return out
    return prune(tree)


def conflicts(tpls):
    s = set(tpls)
    for a in tpls:
        for b in items[a]["_props"].get("ConflictingItems", []) or []:
            if b in s and b != a: return a, b
    return None


def pick_mag(w):
    slot = next((s for s in items[w]["_props"]["Slots"] if s["_name"] == "mod_magazine"), None)
    cands = [t for t in slot["_props"]["filters"][0]["Filter"] if t in items and MAG in parents(t)]
    cap = lambda t: (items[t]["_props"].get("Cartridges") or [{"_max_count": 0}])[0]["_max_count"]
    m = max(cands, key=lambda t: (cap(t), float(items[t]["_props"].get("Ergonomics", 0) or 0)))
    return m, cap(m), set(items[m]["_props"]["Cartridges"][0]["_props"]["filters"][0]["Filter"])


def pick_ammo(caliber, allowed):
    c = [k for k, v in items.items() if v["_parent"] == AMMO and v["_props"].get("Caliber") == caliber and k in allowed]
    return max(c, key=lambda k: (items[k]["_props"].get("PenetrationPower", 0), items[k]["_props"].get("Damage", 0)))


rng = random.Random(20261122)
new_id = lambda: "".join(rng.choice("0123456789abcdef") for _ in range(24))
out = []
for w, short in WEAPONS:
    banned = set()
    for _ in range(60):
        score, tree = best(w, banned)
        c = conflicts(flatten(tree, []))
        if not c: break
        a, b = c
        banned.add(b if own_score(b) <= own_score(a) else a)
    else:
        raise SystemExit(f"{short}: conflicts not resolved")
    tree = one_sight(tree)
    root = new_id()
    p = items[w]["_props"]
    modes = p.get("weapFireType") or ["single"]
    its = [{"_id": root, "_tpl": w, "upd": {"Repairable": {"Durability": 100, "MaxDurability": 100},
                                             "FireMode": {"FireMode": "fullauto" if "fullauto" in modes else modes[0]}}}]

    def emit(tree, parent):
        for slot, c, ct, req in tree:
            i = new_id(); its.append({"_id": i, "_tpl": c, "parentId": parent, "slotId": slot}); emit(ct, i)
    emit(tree, root)
    mag, cap, allowed = pick_mag(w)
    its.append({"_id": new_id(), "_tpl": mag, "parentId": root, "slotId": "mod_magazine"})
    ammo = pick_ammo(p["ammoCaliber"], allowed)
    tpls = flatten(tree, [])
    rec = sum(float(items[t]["_props"].get("Recoil", 0) or 0) for t in tpls + [mag])
    erg = p.get("Ergonomics", 0) + sum(float(items[t]["_props"].get("Ergonomics", 0) or 0) for t in tpls + [mag])
    out.append({"name": short, "weapon": name(w), "root": root, "caliber": p["ammoCaliber"], "ammo": ammo, "items": its})
    print(f"{short:12} recoil up {p.get('RecoilForceUp')} -> {p.get('RecoilForceUp', 0) * (1 + rec / 100):.0f} ({rec:+.0f}%), "
          f"ergo {erg:.0f}, {len(tpls)} parts, mag {cap}, ammo {name(ammo)} (pen {items[ammo]['_props']['PenetrationPower']})")

json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("written", os.path.abspath(OUT))
