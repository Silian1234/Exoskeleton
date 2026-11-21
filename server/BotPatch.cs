// Post-processes bots returned by /client/game/bot/generate (BotController.Generate).
// Needed because Progressive Bot System (APBS) generates loadouts itself and ignores the bot DB.
//
// PMCs: the SAIN personality is rolled HERE with SAIN's own formula and the preset table the client reported (SainRoller),
// then forced on the client through an invisible nickname marker (SAIN NicknamePersonalities).
// The total personality distribution is unchanged; a share (default 20%) of the rolled GigaChads
// gets the full FBA armor set (all slots, all class 5 or all class 6).
// TEST MODE (config): every Scav (assault) also gets a full set.
using System;
using System.Collections.Generic;
using Path = System.IO.Path;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using HarmonyLib;
using SPTarkov.DI.Annotations;
using SPTarkov.Server.Core.Controllers;
using SPTarkov.Server.Core.DI;
using SPTarkov.Server.Core.Helpers;
using SPTarkov.Server.Core.Helpers.Items;
using SPTarkov.Server.Core.Models.Common;
using SPTarkov.Server.Core.Models.Eft.Common.Tables;
using SPTarkov.Server.Core.Models.Utils;
using SPTarkov.Server.Core.Services;
using System.Threading;
using SPTarkov.Common.Models.Logging;
using SPTarkov.Server.Core.Models.Spt.Tables;

namespace FullBodyArmor;

[Injectable(InjectionType.Singleton, OnLoadOrder.Preload + 2)]
public class FbaBotPatch(ISptLogger<FbaBotPatch> logger, TemplateTable templates, BotTable botTable, ItemHelper itemHelper) : IOnLoad
{
    private static FbaBotPatch _instance;
    private ISptLogger<FbaBotPatch> Log => logger;
    private BossKit _kit;
    private Dictionary<MongoId, MongoId> _magSwap, _ammoSwap;   // sanitize.json: Ares' magazines / HyperLethal ammo -> normal
    private readonly Random _rng = Random.Shared;

    // EFT core.json powers (CalcPower): rifle/carbine, smg, marksman, shotgun/revolver, pistol; armor = 6 * sum of classes
    private static readonly (string Base, double Power)[] WeaponPower =
    {
        ("5447b5f14bdc2d61278b4567", 60), ("5447b5fc4bdc2d87278b4567", 60), // assault rifle, carbine
        ("5447b5e04bdc2d62278b4567", 45),                                    // smg
        ("5447b6194bdc2d67278b4567", 55),                                    // marksman rifle
        ("5447b6094bdc2dc3278b4567", 30), ("617f1ef5e8b54b0998387733", 30), // shotgun, revolver
        ("5447b5cf4bdc2d65278b4567", 20),                                    // pistol
    };
    private static readonly string[] ArmorSlots = { "Headwear", "TacticalVest", "ArmorVest", "Eyewear", "FaceCover" };

    public Task OnLoadAsync(CancellationToken cancellationToken)
    {
        _instance = this;
        var target = AccessTools.Method(typeof(BotController), nameof(BotController.Generate));
        var post = typeof(FbaBotPatch).GetMethod(nameof(Postfix), BindingFlags.Static | BindingFlags.NonPublic);
        new Harmony("com.silian.exoskeleton").Patch(target, postfix: new HarmonyMethod(post));
        logger.Info($"[FullBodyArmor] patched {target.DeclaringType?.Name}.{target.Name}");

        if (FullBodyArmorLoader.ArmorReady)
        {
            try
            {
                var preset = SainRoller.Init(Path.GetDirectoryName(typeof(FbaBotPatch).Assembly.Location)!);
                logger.Info(preset == null
                    ? "[FullBodyArmor] waiting for the FBA client to report the SAIN preset (no saved sain-assignments.json yet)"
                    : $"[FullBodyArmor] SAIN personalities: saved table of preset {preset}");
            }
            catch (Exception ex) { logger.Warning($"[FullBodyArmor] sain-assignments.json ignored: {ex.Message}"); }
        }
        try { LoadSanitize(); }
        catch (Exception ex)
        {
            _magSwap = new();
            _ammoSwap = new();
            logger.Error($"[FullBodyArmor] sanitize.json not applied: {ex.Message}");
        }
        return Task.CompletedTask;
    }

    private static void Postfix(ref Task<IEnumerable<BotBase>> __result)
    {
        __result = Wrap(__result);
    }

    private static async Task<IEnumerable<BotBase>> Wrap(Task<IEnumerable<BotBase>> original)
    {
        var bots = (await original)?.ToList();
        try { _instance.Process(bots); }
        catch (Exception ex) { _instance.Log.Error($"[FullBodyArmor] bot post-process failed: {ex}"); }
        return bots;
    }

    private void Process(List<BotBase> bots)
    {
        if (bots == null) return;
        var cfg = FullBodyArmorLoader.Config;
        var sain = cfg.GigaChadArmorEnabled && FullBodyArmorLoader.ArmorReady ? SainRoller.Current : null;
        int sanitized = 0, scavs = 0, pmcs = 0, giga = 0, armored = 0;
        foreach (var bot in bots)
        {
            try
            {
                sanitized += Sanitize(bot);
                var role = bot?.Info?.Settings?.Role;
                if (role == null) continue;

                if (FullBodyArmorLoader.TestModeOn && role.Equals("assault", StringComparison.OrdinalIgnoreCase))
                {
                    if (Equip(bot, FullBodyArmorLoader.FullSet(_rng.Next(2)))) scavs++;
                    continue;
                }

                if (sain == null || !role.StartsWith("pmc", StringComparison.OrdinalIgnoreCase)) continue;
                pmcs++;
                var personality = sain.Roll(role, bot.Info.Level ?? 1, Power(bot), _rng);
                Mark(bot, personality);
                if (personality != SainRoller.GigaChad) continue;
                giga++;
                if (_rng.NextDouble() >= cfg.ArmoredGigaChadShare ||
                    !Equip(bot, FullBodyArmorLoader.FullSet(_rng.NextDouble() < cfg.Class6Share ? 1 : 0))) continue;

                armored++;
                (_kit ??= new BossKit(templates, botTable, itemHelper, logger)).Apply(bot, _rng);
            }
            catch (Exception ex)
            {
                logger.Error($"[FullBodyArmor] bot post-process failed for {bot?.Info?.Nickname ?? "<unknown>"}: {ex}");
            }
        }
        if (sanitized > 0) logger.Info($"[FullBodyArmor] sanitized {sanitized} Ares' magazines / HyperLethal rounds in generated bots");
        if (scavs > 0) logger.Warning($"[FullBodyArmor] TEST MODE: equipped {scavs} Scavs with the FBA carrier");
        if (pmcs > 0) logger.Info($"[FullBodyArmor] PMCs {pmcs}: GigaChads {giga}, armored {armored}");
    }

    private void LoadSanitize()
    {
        _magSwap = new(); _ammoSwap = new();
        var path = Path.Combine(Path.GetDirectoryName(typeof(FbaBotPatch).Assembly.Location)!, "sanitize.json");
        if (!System.IO.File.Exists(path)) { logger.Warning("[FullBodyArmor] sanitize.json not found: Ares' mags / HyperLethal ammo are not cleaned"); return; }
        using var doc = System.Text.Json.JsonDocument.Parse(System.IO.File.ReadAllText(path));
        var db = templates.Items;
        foreach (var (key, dict) in new[] { ("magazines", _magSwap), ("ammo", _ammoSwap) })
            foreach (var kv in doc.RootElement.GetProperty(key).EnumerateObject())
            {
                var from = new MongoId(kv.Name); var to = new MongoId(kv.Value.GetString()!);
                if (db.ContainsKey(from) && db.ContainsKey(to)) dict[from] = to;
            }
        logger.Info($"[FullBodyArmor] sanitize: {_magSwap.Count} Ares' magazines, {_ammoSwap.Count} HyperLethal ammo types");
    }

    /// <summary>Replace Ares' magazines and HyperLethal ammo in a generated bot; returns how many items were changed.</summary>
    private int Sanitize(BotBase bot)
    {
        var items = bot?.Inventory?.Items;
        if (items == null) return 0;
        var db = templates.Items;
        int n = 0;
        foreach (var it in items.ToList())
        {
            if (_ammoSwap.TryGetValue(it.Template, out var a)) { it.Template = a; n++; continue; }
            if (!_magSwap.TryGetValue(it.Template, out var m)) continue;
            it.Template = m; n++;
            int cap = (int)(db[m].Properties?.Cartridges?.FirstOrDefault()?.MaxCount ?? 0);
            if (cap <= 0) continue;
            var id = it.Id.ToString();
            double left = cap;   // several stacks may share one magazine: clamp the total
            var drop = new List<Item>();
            foreach (var c in items.Where(c => c.ParentId == id && c.SlotId == "cartridges").ToList())
            {
                var cnt = c.Upd?.StackObjectsCount ?? 1;
                if (left <= 0) { drop.Add(c); continue; }
                if (cnt > left) { c.Upd ??= new Upd(); c.Upd.StackObjectsCount = left; cnt = left; }
                left -= cnt;
            }
            foreach (var c in drop) items.Remove(c);
        }
        return n;
    }

    private static void Mark(BotBase bot, int personality)
    {
        var m = SainRoller.Marker(personality);
        bot.Info.Nickname = (bot.Info.Nickname ?? "") + m;
        if (bot.Info.LowerNickname != null) bot.Info.LowerNickname += m;
    }

    /// <summary>EFT PlayerAIDataClass.CalcPower: weapon-in-hands power + ARMOR_CLASS_COEF(6) * sum of armor classes.</summary>
    private double Power(BotBase bot)
    {
        var items = bot.Inventory.Items;
        var eq = bot.Inventory.Equipment?.ToString();
        var db = templates.Items;
        double weapon = 0;
        var gun = items.FirstOrDefault(i => i.ParentId == eq && i.SlotId == "FirstPrimaryWeapon")
                  ?? items.FirstOrDefault(i => i.ParentId == eq && i.SlotId == "Holster");
        if (gun != null)
            foreach (var (b, pw) in WeaponPower)
                if (itemHelper.IsOfBaseclass(gun.Template, new MongoId(b))) { weapon = pw; break; }

        double armor = 0;
        var roots = items.Where(i => i.ParentId == eq && ArmorSlots.Contains(i.SlotId)).Select(i => i.Id.ToString()).ToHashSet();
        var all = new HashSet<string>(roots);
        bool added = true;
        while (added)
        {
            added = false;
            foreach (var i in items)
                if (i.ParentId != null && all.Contains(i.ParentId) && all.Add(i.Id.ToString())) added = true;
        }
        foreach (var i in items)
            if (all.Contains(i.Id.ToString()) && db.TryGetValue(i.Template, out var t) && (t.Properties?.ArmorClass ?? 0) > 0)
                armor += t.Properties.ArmorClass.Value;
        return weapon + 6 * armor;
    }

    /// <summary>Replace the bot's ArmorVest with the FBA carrier filled with the given pieces (slot -> template).</summary>
    public bool Equip(BotBase bot, Dictionary<string, string> plates)
    {
        var inv = bot.Inventory;
        var eq = inv.Equipment?.ToString();
        if (eq == null || !FullBodyArmorLoader.ArmorReady) return false;
        var items = inv.Items;
        var db = templates.Items;
        Item Make(string tpl, string parent, string slot)
        {
            var max = db[new MongoId(tpl)].Properties?.MaxDurability ?? 0;
            return new Item
            {
                Id = new MongoId(),
                Template = new MongoId(tpl),
                ParentId = parent,
                SlotId = slot,
                Upd = max > 0 ? new Upd { Repairable = new UpdRepairable { Durability = max, MaxDurability = max } } : null
            };
        }

        var carrier = Make(FullBodyArmorLoader.Carrier, eq, "ArmorVest");
        var cid = carrier.Id.ToString();
        var replacements = plates.Select(kv => Make(kv.Value, cid, kv.Key)).Prepend(carrier).ToList();

        var old = items.FirstOrDefault(i => i.ParentId == eq && i.SlotId == "ArmorVest");
        if (old != null)
        {
            var remove = new HashSet<string> { old.Id.ToString() };
            bool added = true;
            while (added)
            {
                added = false;
                foreach (var i in items)
                    if (i.ParentId != null && remove.Contains(i.ParentId) && remove.Add(i.Id.ToString())) added = true;
            }
            items.RemoveAll(i => remove.Contains(i.Id.ToString()));
        }

        items.AddRange(replacements);
        return true;
    }
}
