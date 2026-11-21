// Extra kit for armored GigaChads ("Tagilla on max"):
//  - Tagilla's skills (bots/types/bosstagilla.json -> skills.Common, max values)
//  - Tagilla's welding mask "ZABEY" (Labyrinth, class 6, whole head + neck) instead of helmet / face cover / eyewear
//  - one of the user's Hephaestus builds (weapons.json, sanitised: no Ares' mags, no HyperLethal ammo),
//    magazines filled with the best AP ammo, a chambered round, spare ammo in the secured container.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using SPTarkov.Server.Core.Helpers;
using SPTarkov.Server.Core.Helpers.Items;
using SPTarkov.Server.Core.Models.Common;
using SPTarkov.Server.Core.Models.Eft.Common.Tables;
using SPTarkov.Server.Core.Models.Enums;
using SPTarkov.Server.Core.Models.Utils;
using SPTarkov.Server.Core.Services;
using Path = System.IO.Path;
using System.Threading;
using SPTarkov.Common.Models.Logging;
using SPTarkov.Server.Core.Models.Spt.Tables;

namespace FullBodyArmor;

public class BossKit
{
    public const string Zabey = "678f84bb9e85556ca60f0362";      // original (unlootable, Labyrinth boss)
    public const string ZabeyFba = "9bb4888f32531e3d322e76f6";   // lootable FBA copy, created by FullBodyArmorLoader
    private const int SpareMagCount = 4;
    private const string MagBase = "5448bc234bdc2d3c308b4569";
    private const int SpareMagazines = 8;

    private record Build(string Name, string Weapon, string Ammo, List<JsonElement> Items, string Root);

    private readonly List<Build> _builds = new();
    private readonly TemplateTable _templates;
    private readonly BotTable _bots;
    private readonly ItemHelper _itemHelper;
    private readonly ISptLogger<FbaBotPatch> _log;

    public BossKit(TemplateTable templates, BotTable bots, ItemHelper itemHelper, ISptLogger<FbaBotPatch> log)
    {
        _templates = templates; _bots = bots; _itemHelper = itemHelper; _log = log;
        var path = Path.Combine(Path.GetDirectoryName(typeof(BossKit).Assembly.Location)!, "weapons.json");
        if (!File.Exists(path)) { log.Warning("[FullBodyArmor] weapons.json not found: armored GigaChads keep their weapon"); return; }
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        var items = templates.Items;
        foreach (var b in doc.RootElement.EnumerateArray())
        {
            var its = b.GetProperty("items").EnumerateArray().Select(e => e.Clone()).ToList();
            var ammo = b.GetProperty("ammo").GetString();
            var missing = its.Select(e => e.GetProperty("_tpl").GetString()).Append(ammo).Where(t => t == null || !items.ContainsKey(new MongoId(t))).ToList();
            if (missing.Count > 0) { log.Warning($"[FullBodyArmor] build {b.GetProperty("name")} skipped, unknown items: {string.Join(",", missing)}"); continue; }
            _builds.Add(new Build(b.GetProperty("name").GetString(), b.GetProperty("weapon").GetString(), ammo, its, b.GetProperty("root").GetString()));
        }
        log.Info($"[FullBodyArmor] boss kit: {_builds.Count} weapon builds ({string.Join(", ", _builds.Select(x => x.Weapon))})");
    }

    public void Apply(BotBase bot, Random rng)
    {
        Skills(bot);
        Helmet(bot);
        if (_builds.Count > 0) Weapon(bot, _builds[rng.Next(_builds.Count)]);
    }

    private void Skills(BotBase bot)
    {
        if (!_bots.Types.TryGetValue("bosstagilla", out var tag) || tag.BotSkills?.Common == null) return;
        var list = (bot.Skills?.Common ?? Enumerable.Empty<CommonSkill>()).ToList();
        foreach (var (name, mm) in tag.BotSkills.Common)
        {
            if (!Enum.TryParse<SkillTypes>(name, out var id)) continue;
            list.RemoveAll(s => s.Id == id);
            list.Add(new CommonSkill { Id = id, Progress = mm.Max, PointsEarnedDuringSession = 0, LastAccess = 0 });
        }
        bot.Skills ??= new Skills { Mastering = new List<MasterySkill>(), Points = 0 };
        bot.Skills.Common = list;
    }

    private static void RemoveSlot(List<Item> items, string eq, string slot)
    {
        var root = items.FirstOrDefault(i => i.ParentId == eq && i.SlotId == slot);
        if (root == null) return;
        var remove = new HashSet<string> { root.Id.ToString() };
        bool added = true;
        while (added)
        {
            added = false;
            foreach (var i in items)
                if (i.ParentId != null && remove.Contains(i.ParentId) && remove.Add(i.Id.ToString())) added = true;
        }
        items.RemoveAll(i => remove.Contains(i.Id.ToString()));
    }

    private void Helmet(BotBase bot)
    {
        if (!FullBodyArmorLoader.MaskReady ||
            !_templates.Items.TryGetValue(new MongoId(ZabeyFba), out var mask) || mask.Properties == null) return;
        var items = bot.Inventory.Items;
        var eq = bot.Inventory.Equipment.ToString();
        foreach (var s in new[] { "Headwear", "FaceCover", "Eyewear" }) RemoveSlot(items, eq, s); // ZABEY conflicts with helmets, blocks eyewear
        var max = mask.Properties.MaxDurability ?? 100;
        items.Add(new Item
        {
            Id = new MongoId(), Template = new MongoId(ZabeyFba), ParentId = eq, SlotId = "FaceCover",
            Upd = new Upd { Repairable = new UpdRepairable { Durability = max, MaxDurability = max } }
        });
    }

    private bool IsMagazine(MongoId tpl) => _itemHelper.IsOfBaseclass(tpl, new MongoId(MagBase));

    private bool GridAccepts(Grid g, MongoId tpl)
    {
        var f = g.Properties?.Filters?.FirstOrDefault();
        if (f == null) return true;
        bool inc = f.Filter == null || f.Filter.Count == 0 || f.Filter.Any(x => _itemHelper.IsOfBaseclass(tpl, x) || x == tpl);
        bool exc = f.ExcludedFilter != null && f.ExcludedFilter.Any(x => _itemHelper.IsOfBaseclass(tpl, x) || x == tpl);
        return inc && !exc;
    }

    private (int W, int H) Size(MongoId tpl)
    {
        var p = _templates.Items[tpl].Properties;
        return (p?.Width ?? 1, p?.Height ?? 1);
    }

    /// <summary>Remove magazines that don't fit the new weapon from rig/pockets/backpack, then pack SpareMagCount full magazines.</summary>
    private const string RaidBackpack = "5df8a4d786f77412672a1e3b"; // 6Sh118 raid backpack (EMR), 48 cells

    private void PackSpareMags(BotBase bot, MongoId magTpl, MongoId ammo)
    {
        int placed = PackInto(bot, magTpl, ammo, SpareMagCount);
        if (placed >= SpareMagCount) return;
        // not enough room: give a big empty raid backpack (replaces the current one) and pack the rest there
        var items = bot.Inventory.Items;
        var eq = bot.Inventory.Equipment.ToString();
        int inOldBackpack = 0;
        var bpk = items.FirstOrDefault(i => i.ParentId == eq && i.SlotId == "Backpack");
        if (bpk != null) inOldBackpack = items.Count(i => i.ParentId == bpk.Id.ToString() && i.Template == magTpl);
        RemoveSlot(items, eq, "Backpack");
        items.Add(new Item { Id = new MongoId(), Template = new MongoId(RaidBackpack), ParentId = eq, SlotId = "Backpack" });
        placed = placed - inOldBackpack + PackInto(bot, magTpl, ammo, SpareMagCount - (placed - inOldBackpack));
        if (placed < SpareMagCount) _log.Warning($"[FullBodyArmor] only {placed}/{SpareMagCount} spare magazines fit for {magTpl} even with a raid backpack");
    }

    /// <summary>Remove foreign magazines from rig/pockets/backpack and pack up to `want` full magazines; returns how many were placed.</summary>
    private int PackInto(BotBase bot, MongoId magTpl, MongoId ammo, int want)
    {
        var items = bot.Inventory.Items;
        var eq = bot.Inventory.Equipment.ToString();
        var db = _templates.Items;
        var cap = Capacity(db[magTpl]);
        int placed = 0;
        foreach (var slot in new[] { "TacticalVest", "Pockets", "Backpack" })
        {
            var cont = items.FirstOrDefault(i => i.ParentId == eq && i.SlotId == slot);
            if (cont == null) continue;
            var cid = cont.Id.ToString();
            // drop old magazines (and their cartridges) from this container
            var oldMags = items.Where(i => i.ParentId == cid && IsMagazine(i.Template) && i.Template != magTpl).Select(i => i.Id.ToString()).ToHashSet();
            items.RemoveAll(i => oldMags.Contains(i.Id.ToString()) || (i.ParentId != null && oldMags.Contains(i.ParentId)));

            foreach (var g in db[cont.Template].Properties?.Grids ?? Enumerable.Empty<Grid>())
            {
                if (placed >= want) return placed;
                if (!GridAccepts(g, magTpl)) continue;
                int gw = g.Properties?.CellsH ?? 0, gh = g.Properties?.CellsV ?? 0;
                var occ = new bool[gw, gh];
                foreach (var i in items.Where(i => i.ParentId == cid && i.SlotId == g.Name))
                {
                    if (i.Location is not ItemLocation loc) continue;
                    var (w, h) = Size(i.Template);
                    if (loc.R == ItemRotation.Vertical) (w, h) = (h, w);
                    for (int x = loc.X ?? 0; x < Math.Min(gw, (loc.X ?? 0) + w); x++)
                    for (int y = loc.Y ?? 0; y < Math.Min(gh, (loc.Y ?? 0) + h); y++) occ[x, y] = true;
                }
                var (mw, mh) = Size(magTpl);
                for (int y = 0; y < gh && placed < want; y++)
                for (int x = 0; x < gw && placed < want; x++)
                foreach (var rot in new[] { ItemRotation.Horizontal, ItemRotation.Vertical })
                {
                    var (w, h) = rot == ItemRotation.Horizontal ? (mw, mh) : (mh, mw);
                    if (x + w > gw || y + h > gh) continue;
                    bool free = true;
                    for (int xx = x; xx < x + w && free; xx++) for (int yy = y; yy < y + h; yy++) if (occ[xx, yy]) { free = false; break; }
                    if (!free) continue;
                    for (int xx = x; xx < x + w; xx++) for (int yy = y; yy < y + h; yy++) occ[xx, yy] = true;
                    var mag = new Item { Id = new MongoId(), Template = magTpl, ParentId = cid, SlotId = g.Name,
                        Location = new ItemLocation { X = x, Y = y, R = rot } };
                    items.Add(mag);
                    if (cap > 0) items.Add(new Item { Id = new MongoId(), Template = ammo, ParentId = mag.Id.ToString(), SlotId = "cartridges", Location = 0, Upd = new Upd { StackObjectsCount = cap } });
                    placed++;
                    break;
                }
            }
        }
        return placed;
    }

    private int Capacity(TemplateItem t) => (int)(t.Properties?.Cartridges?.FirstOrDefault()?.MaxCount ?? 0);

    private void Weapon(BotBase bot, Build b)
    {
        var items = bot.Inventory.Items;
        var eq = bot.Inventory.Equipment.ToString();
        var db = _templates.Items;
        RemoveSlot(items, eq, "FirstPrimaryWeapon");

        var map = new Dictionary<string, string>();
        foreach (var e in b.Items) map[e.GetProperty("_id").GetString()!] = new MongoId().ToString();
        var ammo = new MongoId(b.Ammo);
        int magCap = 0;
        MongoId? mainMag = null;
        foreach (var e in b.Items)
        {
            var oldId = e.GetProperty("_id").GetString()!;
            var tpl = new MongoId(e.GetProperty("_tpl").GetString()!);
            bool isRoot = oldId == b.Root;
            var it = new Item
            {
                Id = new MongoId(map[oldId]),
                Template = tpl,
                ParentId = isRoot ? eq : map[e.GetProperty("parentId").GetString()!],
                SlotId = isRoot ? "FirstPrimaryWeapon" : e.GetProperty("slotId").GetString(),
            };
            if (isRoot)
            {
                var max = db[tpl].Properties?.MaxDurability ?? 100;
                var modes = db[tpl].Properties?.WeapFireType?.ToList() ?? new List<string>();
                it.Upd = new Upd
                {
                    Repairable = new UpdRepairable { Durability = max, MaxDurability = max },
                    FireMode = new UpdFireMode { FireMode = modes.Contains("fullauto") ? "fullauto" : modes.FirstOrDefault() ?? "single" }
                };
            }
            items.Add(it);

            // fill magazines (detachable boxes/drums/belts and internal mags are all MagazineItemClass)
            if (IsMagazine(tpl))
            {
                if (!isRoot && e.GetProperty("parentId").GetString() == b.Root && it.SlotId == "mod_magazine") mainMag = tpl;
                int cap = Capacity(db[tpl]);
                if (cap > 0)
                {
                    magCap = Math.Max(magCap, cap);
                    items.Add(new Item
                    {
                        Id = new MongoId(), Template = ammo, ParentId = it.Id.ToString(), SlotId = "cartridges",
                        Location = 0, Upd = new Upd { StackObjectsCount = cap }
                    });
                }
            }
        }

        // chambered round
        var rootTpl = db[new MongoId(b.Items.First(e => e.GetProperty("_id").GetString() == b.Root).GetProperty("_tpl").GetString()!)];
        if (rootTpl.Properties?.Chambers?.Any() == true)
            items.Add(new Item { Id = new MongoId(), Template = ammo, ParentId = map[b.Root], SlotId = "patron_in_weapon", Upd = new Upd { StackObjectsCount = 1 } });

        // spare magazines: AI reloads by swapping magazines from rig / pockets / backpack
        if (mainMag.HasValue) PackSpareMags(bot, mainMag.Value, ammo);

        // spare loose ammo in the secured container
        var sc = items.FirstOrDefault(i => i.ParentId == eq && i.SlotId == "SecuredContainer");
        if (sc == null) return;
        var grid = db[sc.Template].Properties?.Grids?.FirstOrDefault();
        if (grid == null) return;
        var w = grid.Properties?.CellsH ?? 1; var h = grid.Properties?.CellsV ?? 1;
        var scId = sc.Id.ToString();
        items.RemoveAll(i => i.ParentId == scId);
        var stack = (int)(db[ammo].Properties?.StackMaxSize ?? 60);
        int rounds = Math.Max(magCap, 30) * SpareMagazines;
        int stacks = Math.Min(w * h, (rounds + stack - 1) / stack);
        for (int n = 0; n < stacks; n++)
            items.Add(new Item
            {
                Id = new MongoId(), Template = ammo, ParentId = scId, SlotId = grid.Name,
                Location = new ItemLocation { X = n % w, Y = n / w, R = ItemRotation.Horizontal },
                Upd = new Upd { StackObjectsCount = Math.Min(stack, rounds - n * stack) }
            });
    }
}
