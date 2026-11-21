// EXO exoskeletons, three tiers (client buffs in FullBodyArmorClient, per tier):
//   T1 "construction"  e5f82a1e0c7846b9a4130de1  Kora-Kulon class 3 soft front/back,               6 kg,  Ragman LL2   275 000
//   T2 "military"      bfcd6ff9414d8611685db39f  Kora-Kulon class 3 soft front/back,               8 kg,  Ragman LL3   550 000
//   T3 "assault"       eb8f6601528512fcd0b0fd1d  built-in TITANIUM plates on all FBA zones:
//                      torso front/back class 4, sides+armpits / neck / shoulders / forearms / groin / thighs / calves class 3,
//                      durability 55 each (Titan repairs badly: 6-10 % max-durability loss per repair), ~21 kg, Ragman LL4 1 100 000
// All tiers conflict with ANY armored gear (helmets, armored masks/glasses, ballistic rigs): the frame trades armor for buffs.
// Models: item_equipment_exoskeleton[_t2|_t3].bundle; a tier falls back to the T1 model while its bundle is not installed.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using SPTarkov.DI.Annotations;
using SPTarkov.Server.Core.DI;
using SPTarkov.Server.Core.Models.Common;
using SPTarkov.Server.Core.Models.Eft.Common;
using SPTarkov.Server.Core.Models.Eft.Common.Tables;
using SPTarkov.Server.Core.Models.Enums;
using SPTarkov.Server.Core.Models.Spt.Mod;
using SPTarkov.Server.Core.Models.Utils;
using SPTarkov.Server.Core.Services;
using SPTarkov.Server.Core.Services.Mod;
using Path = System.IO.Path;

namespace FullBodyArmor;

[Injectable(InjectionType.Singleton, null, OnLoadOrder.PostDBModLoader + 20)]
public class ExoskeletonLoader(DatabaseService db, CustomItemService itemService, ISptLogger<ExoskeletonLoader> log) : IOnLoad
{
    public const string TemplateId = "e5f82a1e0c7846b9a4130de1";   // T1 (kept: existing items stay valid)
    public const string T2Id = "bfcd6ff9414d8611685db39f";
    public const string T3Id = "eb8f6601528512fcd0b0fd1d";
    private const string Donor = "64be79c487d1510151095552";        // NPP KlASS Kora-Kulon (class 3 soft front/back liners)
    private const string InsertDonor = "6575d9a79e27f4a85e08112d";  // Redut-T5 built-in soft insert (BuiltInInserts parent)
    private const string Headwear = "5a341c4086f77401f2541505";
    private const string Rig = "5448e5284bdc2dcb718b4567";
    private const string FaceCover = "5a341c4686f77469e155819e";
    private const string Eyewear = "5448e5724bdc2ddf718b4568";
    private const string Ragman = "5ac3b934156ae10c4430e83c";
    private const string Roubles = "5449016a4bdc2d6f028b456f";
    private const string ArmorHandbook = "5b5f701386f774093f2ecf0f";
    private const string ModelDir = "assets/content/items/equipment/exoskeleton/";

    private record Tier(string Id, string Offer, string Preset, string Suffix, int Price, int Loyalty, double Weight,
        string Key, string ShortEn);

    private static readonly Tier[] Tiers =
    {
        new(TemplateId, "e5f82a1e0c7846b9a4130de2", "e5f82a1e0c7846b9a4130de3", "", 275000, 2, 6,
            "exo1", "EXO-1"),
        new(T2Id, "9df6f443726dff0861e4089a", "e486c12546ee1ace5e01c587", "_t2", 550000, 3, 8,
            "exo2", "EXO-2"),
        new(T3Id, "4dd22299c0776d6175527aff", "c5554406104440644ba6a9a5", "_t3", 1100000, 4, 21,
            "exo3", "EXO-3"),
    };

    // In-game texts of tiers and inserts live in locales.json (Texts); En/Ru here are internal labels only.
    // T3 built-in titanium inserts: one template per zone type, the slot restricts the side (verified in raid for FBA)
    private record Insert(string Id, string Key, int Class, string[] Colliders, string En, string Ru);
    private static readonly Insert[] Inserts =
    {
        new("beb0fd868596ef4cf3f67a37", "torso", 4, new[] { "RibcageUp", "RibcageLow", "SpineTop", "SpineDown" }, "torso", "торс"),
        new("54ef898aa7afbb974f39be71", "side", 3, new[] { "LeftSideChestDown", "RightSideChestDown", "LeftSideChestUp", "RightSideChestUp" }, "side", "бок"),
        new("9f5b09b82a9828adc4fe6b51", "collar", 3, new[] { "NeckFront", "NeckBack" }, "collar", "воротник"),
        new("1da3073e34d1820a4660426b", "shoulder", 3, new[] { "LeftUpperArm", "RightUpperArm" }, "shoulder", "плечо"),
        new("ea7662eb542901b68e24672e", "forearm", 3, new[] { "LeftForearm", "RightForearm" }, "forearm", "предплечье"),
        new("873c27ba8563d9077652e2f8", "groin", 3, new[] { "Pelvis", "PelvisBack" }, "groin", "пах"),
        new("524c7de5f2093b7ecc685086", "thigh", 3, new[] { "LeftThigh", "RightThigh" }, "thigh", "бедро"),
        new("12716eb6345fccff8fc03c7b", "calf", 3, new[] { "LeftCalf", "RightCalf" }, "calf", "голень"),
    };
    private static readonly (string Slot, string Id, string Insert, string[] Colliders)[] T3Slots =
    {
        ("Soft_armor_front", "f74835e1fdfedc622aa28610", "torso", new[] { "RibcageUp", "RibcageLow" }),
        ("Soft_armor_back", "6ed1ab8697191656d10909b5", "torso", new[] { "SpineTop", "SpineDown" }),
        ("Soft_armor_left", "6bca264dda7440aa40acf647", "side", new[] { "LeftSideChestDown", "LeftSideChestUp" }),
        ("soft_armor_right", "0875b01947d4c19a725f463a", "side", new[] { "RightSideChestDown", "RightSideChestUp" }),
        ("Collar", "381137dfd6f5eef8348a064e", "collar", new[] { "NeckFront", "NeckBack" }),
        ("Shoulder_l", "ac693ae91928cadbfccf5c63", "shoulder", new[] { "LeftUpperArm" }),
        ("Shoulder_r", "51462962946f24cb6100fed6", "shoulder", new[] { "RightUpperArm" }),
        ("Forearm_l", "0b06b7a34e4d930a40d288bf", "forearm", new[] { "LeftForearm" }),
        ("Forearm_r", "f9f657c1d3474165f389d499", "forearm", new[] { "RightForearm" }),
        ("Groin", "468b1b0ea52d75d0ae61a163", "groin", new[] { "Pelvis" }),
        ("Groin_back", "cc3097df309f02ae23f9a857", "groin", new[] { "PelvisBack" }),
        ("Thigh_l", "b5d63904d58cb03f60c7c76d", "thigh", new[] { "LeftThigh" }),
        ("Thigh_r", "b90310e2ac56783aec531f74", "thigh", new[] { "RightThigh" }),
        ("Calf_l", "c36be6d61a26ce71942047e2", "calf", new[] { "LeftCalf" }),
        ("Calf_r", "74f96970640788c6eb1f214f", "calf", new[] { "RightCalf" }),
    };
    private const double InsertDurability = 55;   // vanilla titanium class 4 plate (KibaArms Titan); same for all zones
    private const double InsertBlunt = 0.14;      // vanilla titanium plate blunt throughput

    public Task OnLoad()
    {
        try { Register(); }
        catch (Exception ex) { log.Error($"[Exoskeleton] registration failed: {ex}"); }
        return Task.CompletedTask;
    }

    private void Register()
    {
        var items = db.GetItems();
        foreach (var t in Tiers)
            if (items.ContainsKey(new MongoId(t.Id))) throw new InvalidOperationException($"template {t.Id} already exists");

        var source = items[new MongoId(Donor)];
        var liners = BuildLinerSlots(items, source);
        MakeInserts(items);

        var conflicts = items.Values
            .Where(t => t.Type == "Item" &&
                (IsUnder(t, Headwear, items) || IsUnder(t, Rig, items) || IsUnder(t, FaceCover, items) || IsUnder(t, Eyewear, items)) &&
                HasArmor(t, items))
            .Select(t => t.Id).ToHashSet();

        var assort = db.GetTrader(new MongoId(Ragman))?.Assort;
        if (assort?.Items == null || assort.BarterScheme == null || assort.LoyalLevelItems == null)
            throw new InvalidOperationException("Ragman assortment unavailable");
        var presets = db.GetGlobals().ItemPresets;
        var bundleDir = Path.Combine(Path.GetDirectoryName(typeof(ExoskeletonLoader).Assembly.Location)!, "bundles");

        foreach (var t in Tiers)
        {
            var id = new MongoId(t.Id);
            var result = itemService.CreateItemFromClone(new NewItemFromCloneDetails
            {
                ItemTplToClone = new MongoId(Donor), NewId = t.Id, ParentId = source.Parent.ToString(),
                HandbookParentId = ArmorHandbook, HandbookPriceRoubles = t.Price, FleaPriceRoubles = t.Price,
                Locales = Texts.Item($"{t.Key}.name", $"{t.Key}.short", $"{t.Key}.desc")
            });
            if (result?.Success != true || !items.TryGetValue(id, out var item) || item.Properties == null)
                throw new InvalidOperationException($"{t.ShortEn} clone failed: " + string.Join("; ", result?.Errors ?? new List<string>()));

            // own model when its bundle is installed, otherwise the T1 model
            var model = ModelDir + $"item_equipment_exoskeleton{t.Suffix}.bundle";
            if (t.Suffix != "" && !File.Exists(Path.Combine(bundleDir, model.Replace('/', Path.DirectorySeparatorChar))))
                model = ModelDir + "item_equipment_exoskeleton.bundle";

            var slots = t.Id == T3Id ? BuildT3Slots() : liners.Select(s => CloneSlot(s, t.Id)).ToList();
            var props = item.Properties;
            props.Prefab = new Prefab { Path = model, Rcid = "" };
            props.Slots = slots;
            props.ConflictingItems = conflicts;
            props.CanSellOnRagfair = false;
            props.SpeedPenaltyPercent = 0;
            props.MousePenalty = 0;
            props.WeaponErgonomicPenalty = 0;
            props.Weight = t.Weight;
            if (t.Id == T3Id) props.ArmorMaterial = ArmorMaterial.Titan;

            var offer = new MongoId(t.Offer); var presetId = new MongoId(t.Preset);
            if (presets.ContainsKey(presetId) || assort.BarterScheme.ContainsKey(offer) || assort.LoyalLevelItems.ContainsKey(offer) || assort.Items.Any(i => i.Id == offer))
                throw new InvalidOperationException($"{t.ShortEn}: offer or preset ID already exists");
            var root = new MongoId();
            presets.Add(presetId, new Preset { Id = presetId, Type = "Preset", Name = t.ShortEn, Parent = root, Encyclopedia = id, Items = Kit(root, id, slots, false) });
            assort.Items.AddRange(Kit(offer, id, slots, true));
            assort.BarterScheme.Add(offer, new() { new() { new BarterScheme { Template = new MongoId(Roubles), Count = t.Price } } });
            assort.LoyalLevelItems.Add(offer, t.Loyalty);
            log.Success($"[Exoskeleton] registered {t.ShortEn}: {slots.Count} built-in slots, {conflicts.Count} armored-gear conflicts, model {Path.GetFileName(model)}, Ragman LL{t.Loyalty} {t.Price}");
        }

        List<Item> Kit(MongoId rootId, MongoId tpl, List<Slot> slots, bool forSale)
        {
            var kit = new List<Item> { new() { Id = rootId, Template = tpl, ParentId = forSale ? "hideout" : null,
                SlotId = forSale ? "hideout" : null, Upd = forSale ? new Upd { StackObjectsCount = 10, BuyRestrictionMax = 1, BuyRestrictionCurrent = 0 } : null } };
            foreach (var slot in slots)
            {
                var plate = slot.Properties.Filters.Single().Plate.Value;
                var max = items[plate].Properties.MaxDurability ?? 0;
                kit.Add(new Item { Id = new MongoId(), Template = plate, ParentId = rootId.ToString(), SlotId = slot.Name,
                    Upd = new Upd { Repairable = new UpdRepairable { Durability = max, MaxDurability = max } } });
            }
            return kit;
        }
    }

    private static List<Slot> BuildLinerSlots(Dictionary<MongoId, TemplateItem> items, TemplateItem source)
    {
        var slots = source.Properties.Slots.Where(s => s.Name is "Soft_armor_front" or "Soft_armor_back").ToArray();
        if (slots.Length != 2 || slots[0].Name == slots[1].Name) throw new InvalidOperationException("missing stock front/back liner");
        var list = new List<Slot>();
        foreach (var slot in slots)
        {
            var plate = slot.Properties.Filters.Single().Plate;
            var p = items[plate.Value].Properties;
            var zones = slot.Name == "Soft_armor_front" ? new[] { "RibcageUp", "RibcageLow" } : new[] { "SpineTop", "SpineDown" };
            if (p.ArmorClass != 3 || p.ArmorColliders == null || !zones.ToHashSet().SetEquals(p.ArmorColliders))
                throw new InvalidOperationException($"unexpected liner protection for {slot.Name}");
            list.Add(new Slot
            {
                Id = slot.Id, Name = slot.Name, Prototype = slot.Prototype, Required = true, MergeSlotWithChildren = true,
                Properties = new SlotProperties { Filters = new List<SlotFilter> { new() { Filter = new HashSet<MongoId> { plate.Value }, Plate = plate, Locked = true, ArmorColliders = zones.ToList() } } }
            });
        }
        return list;
    }

    // T1 and T2 share the Kora-Kulon liner slots; slot ids are derived per tier so they stay unique
    private static Slot CloneSlot(Slot s, string parent) => new()
    {
        Id = parent == TemplateId ? s.Id : DeriveId(s.Id, parent), Name = s.Name, Parent = parent, Prototype = s.Prototype,
        Required = s.Required, MergeSlotWithChildren = s.MergeSlotWithChildren, Properties = s.Properties
    };

    private static string DeriveId(string a, string b)
    {
        var bytes = System.Security.Cryptography.MD5.HashData(System.Text.Encoding.ASCII.GetBytes(a + b));
        return Convert.ToHexString(bytes, 0, 12).ToLowerInvariant();
    }

    private void MakeInserts(Dictionary<MongoId, TemplateItem> items)
    {
        var parent = items[new MongoId(InsertDonor)].Parent.ToString();
        foreach (var ins in Inserts)
        {
            var r = itemService.CreateItemFromClone(new NewItemFromCloneDetails
            {
                ItemTplToClone = new MongoId(InsertDonor), NewId = ins.Id, ParentId = parent,
                HandbookParentId = "5b5f704686f77447ec5d76d7", HandbookPriceRoubles = 30000, FleaPriceRoubles = 30000,
                Locales = Texts.Item("insert.name", "insert.short", "insert.desc", ("zone", "@insert." + ins.Key), ("cls", ins.Class.ToString()))
            });
            if (r?.Success != true) throw new InvalidOperationException($"insert {ins.Key} failed: " + string.Join("; ", r?.Errors ?? new List<string>()));
            var p = items[new MongoId(ins.Id)].Properties;
            p.ArmorClass = ins.Class;
            p.ArmorMaterial = ArmorMaterial.Titan;
            p.MaxDurability = InsertDurability; p.Durability = InsertDurability;
            p.ArmorColliders = ins.Colliders.ToList();
            p.ArmorPlateColliders = new List<string>();
            p.BluntThroughput = InsertBlunt;
            p.ArmorType = "Heavy";
            p.Weight = 0;               // weight is on the frame (like vanilla built-in inserts)
            p.CanSellOnRagfair = false;
        }
    }

    private static List<Slot> BuildT3Slots() => T3Slots.Select(s =>
    {
        var plate = new MongoId(Inserts.First(i => i.Key == s.Insert).Id);
        return new Slot
        {
            Id = s.Id, Name = s.Slot, Parent = T3Id, Prototype = "64479fdf9731c8fadc0642c1", Required = true, MergeSlotWithChildren = true,
            Properties = new SlotProperties { Filters = new List<SlotFilter> { new()
            {
                Filter = new HashSet<MongoId> { plate }, Plate = plate, Locked = true,
                ArmorColliders = s.Colliders.ToList(), ArmorPlateColliders = new List<string>(), BluntDamageReduceFromSoftArmor = false
            } } }
        };
    }).ToList();

    private static bool IsUnder(TemplateItem item, string baseClass, Dictionary<MongoId, TemplateItem> items)
    {
        var target = new MongoId(baseClass);
        for (var i = 0; i < 32 && item != null; ++i)
        {
            if (item.Parent == target) return true;
            items.TryGetValue(item.Parent, out item);
        }
        return false;
    }

    private static bool HasArmor(TemplateItem item, Dictionary<MongoId, TemplateItem> items) =>
        (item.Properties?.ArmorClass ?? 0) > 0 ||
        (item.Properties?.Slots?.Any(s => s.Properties?.Filters?.Any(f =>
            f.ArmorColliders?.Any() == true || f.ArmorPlateColliders?.Any() == true ||
            (f.Plate.HasValue && items.TryGetValue(f.Plate.Value, out var part) && (part.Properties?.ArmorClass ?? 0) > 0)) == true) == true);
}
