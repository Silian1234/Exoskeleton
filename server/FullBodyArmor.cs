// FullBodyArmor — modular full-body armor (SPT 4.1.x).
// Carrier = FORT Redut-T5 clone with NO built-in inserts: every slot is removable.
// Pieces: 10 types x classes 5/6, Aramid. One item type fits paired slots (left/right, front/back):
// the client intersects slot colliders with item colliders (verified in raid with FbaArmorProbe).
// Limb/soft pieces use armorColliders (body-part colliders); torso/side plates use armorPlateColliders.
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using SPTarkov.DI.Annotations;
using SPTarkov.Server.Core.DI;
using SPTarkov.Server.Core.Models.Common;
using SPTarkov.Server.Core.Models.Eft.Common.Tables;
using SPTarkov.Server.Core.Models.Enums;
using SPTarkov.Server.Core.Models.Spt.Mod;
using SPTarkov.Server.Core.Models.Utils;
using SPTarkov.Server.Core.Services;
using SPTarkov.Server.Core.Services.Modding.Custom;
using Range = SemanticVersioning.Range;
using Version = SemanticVersioning.Version;
using System.Threading;
using SPTarkov.Common.Models.Logging;
using SPTarkov.Server.Core.Models.Spt.Tables;

namespace FullBodyArmor;

// SPT 4.1: metadata is an IModMetadata record; bundles are picked up from bundles.json next to the DLL.
public record ModMetadata : IModMetadata
{
    public string ModGuid { get; init; } = "com.silian.exoskeleton";
    public string Name { get; init; } = "FullBodyArmor";
    public string Author { get; init; } = "silian";
    public List<string> Contributors { get; init; }
    public Version Version { get; init; } = new("1.1.0");
    public Range SptVersion { get; init; } = new("~4.1.3");
    public List<string> Incompatibilities { get; init; }
    public Dictionary<string, Range> ModDependencies { get; init; }
    public string Url { get; init; } = "https://github.com/Silian1234/Exoskeleton";
    public string License { get; init; } = "MIT";
    public bool HasPrepatcher { get; init; } = false;
}

/// <summary>One armor piece type, available in class 5 and class 6 (index 0 / 1).</summary>
public record Piece(
    string Key, string En, string Ru,
    string[] Colliders, string[] PlateColliders,
    int W, int H, double Blunt,
    string[] Ids, double[] Weight, double[] Speed, double[] Ergo, double[] Mouse);

/// <summary>Carrier slot: name, slot id, piece type, slot colliders, slot plate colliders.</summary>
public record CarrierSlot(string Name, string Id, string Piece, string[] Colliders, string[] PlateColliders, bool BluntReduce);

[Injectable(InjectionType.Singleton, OnLoadOrder.Preload + 1)]
public class FullBodyArmorLoader(
    ISptLogger<FullBodyArmorLoader> logger,
    TemplateTable templates,
    CustomItemService customItemService) : IOnLoad
{
    // vanilla
    private const string RedutT5 = "5ca21c6986f77479963115a7";
    private const string ClonePlate = "656fae5f7c2d57afe200c0d7"; // GAC 3s15m (ArmorPlate class) — only used as a template
    private const string HbArmor = "5b5f701386f774093f2ecf0f";
    private const string HbPlates = "5b5f704686f77447ec5d76d7";
    private const string SlotProto = "64479fdf9731c8fadc0642c1";
    private const string CarrierBundle = "assets/content/items/equipment/fba/item_equipment_fba_carrier.bundle";

    public const string Carrier = "554bc0fb5531ccd849af6506";
    public static bool TestModeOn;
    public static bool ArmorReady { get; private set; }
    public static bool MaskReady { get; private set; }
    private static readonly HashSet<MongoId> ClonedIds = new();
    public static IEnumerable<MongoId> RegisteredIds => ClonedIds;

    // Same durability for every piece of a class (torso = limbs). No vanilla Aramid class 5/6 exists to copy from.
    public static readonly int[] Classes = { 5, 6 };
    public static readonly double[] Durability = { 75, 85 };

    // In-game texts are in locales.json (Texts); the En/Ru labels below are internal only.
    public static readonly Piece[] Pieces =
    {
        new("torso_plate", "Torso armor plate", "Торсовая бронепластина", new string[0],
            new[] { "Plate_Granit_SAPI_chest", "Plate_Granit_SAPI_back" }, 2, 2, 0.30,
            new[] { "82b4d27429a5fd99399fb6fa", "6fefd5b26ac335d567ca9755" },
            new[] { 2.0, 2.8 }, new[] { -1.0, -1.5 }, new[] { -1.0, -1.5 }, new[] { -0.5, -0.5 }),
        new("soft_panel", "Torso soft panel", "Мягкая панель корпуса",
            new[] { "RibcageUp", "RibcageLow", "SpineTop", "SpineDown" }, new string[0], 2, 2, 0.36,
            new[] { "14b50cfc05885d875c6632c4", "0846039c668ce23e8f2a1992" },
            new[] { 1.2, 1.7 }, new[] { -0.5, -0.75 }, new[] { -0.5, -0.75 }, new[] { 0.0, 0.0 }),
        new("side_panel", "Side panel", "Боковая панель",
            new[] { "LeftSideChestDown", "RightSideChestDown", "LeftSideChestUp", "RightSideChestUp" }, new string[0], 1, 2, 0.36,
            new[] { "d27af43d3b5456d1ee0fd111", "737c907f2c27da36b11a70d4" },
            new[] { 0.5, 0.7 }, new[] { -0.25, -0.25 }, new[] { 0.0, 0.0 }, new[] { 0.0, 0.0 }),
        new("collar", "Collar", "Воротник",
            new[] { "NeckFront", "NeckBack" }, new string[0], 2, 1, 0.36,
            new[] { "703e4553c54eaf41ca4503a8", "577eb8a472a4e809df0da032" },
            new[] { 0.35, 0.5 }, new[] { 0.0, 0.0 }, new[] { -0.5, -0.75 }, new[] { -0.5, -0.75 }),
        new("shoulder", "Shoulder pad", "Наплечник",
            new[] { "LeftUpperArm", "RightUpperArm" }, new string[0], 1, 2, 0.36,
            new[] { "5cfbda438d0b92eb94e81f91", "1fa7cf9c7bb8348898a330b5" },
            new[] { 0.45, 0.6 }, new[] { 0.0, 0.0 }, new[] { -0.75, -1.0 }, new[] { -0.25, -0.5 }),
        new("groin", "Groin panel", "Паховая панель",
            new[] { "Pelvis", "PelvisBack" }, new string[0], 2, 1, 0.36,
            new[] { "c030573bc7e880359da2d8c4", "3ef4c409bedad277d84fc355" },
            new[] { 0.45, 0.6 }, new[] { -0.5, -0.75 }, new[] { 0.0, 0.0 }, new[] { 0.0, 0.0 }),
        new("side_plate", "Side armor plate", "Боковая бронепластина", new string[0],
            new[] { "Plate_Granit_SSAPI_side_left_high", "Plate_Granit_SSAPI_side_left_low",
                    "Plate_Granit_SSAPI_side_right_high", "Plate_Granit_SSAPI_side_right_low" }, 1, 1, 0.30,
            new[] { "4abe324c2efd90acc907796a", "759310ddb641a69611156e75" },
            new[] { 0.6, 0.85 }, new[] { -0.5, -0.5 }, new[] { 0.0, 0.0 }, new[] { -0.25, -0.25 }),
        new("thigh", "Thigh armor plate", "Бедренная бронепластина",
            new[] { "LeftThigh", "RightThigh" }, new string[0], 1, 2, 0.36,
            new[] { "f950b3b94783702f8134fc3d", "c465a652415dc5cfe9b1fa6e" },
            new[] { 1.8, 2.5 }, new[] { -1.0, -1.5 }, new[] { 0.0, 0.0 }, new[] { -0.5, -0.5 }),
        new("calf", "Calf armor plate", "Голенная бронепластина",
            new[] { "LeftCalf", "RightCalf" }, new string[0], 1, 2, 0.36,
            new[] { "354274b72104b70253a56df3", "b48cfef239dab289b7e6d452" },
            new[] { 1.0, 1.38 }, new[] { -0.75, -1.0 }, new[] { 0.0, 0.0 }, new[] { 0.0, 0.0 }),
        new("forearm", "Forearm armor plate", "Наручная бронепластина",
            new[] { "LeftForearm", "RightForearm" }, new string[0], 1, 1, 0.36,
            new[] { "59d089a23a0a45c761490fa2", "9bdce17575648290edd39b91" },
            new[] { 0.54, 0.75 }, new[] { 0.0, 0.0 }, new[] { -2.0, -3.0 }, new[] { -0.75, -1.0 }),
    };

    // Slot ids of the 13 Redut slots are kept (cloned); limb slots keep their earlier ids.
    public static readonly CarrierSlot[] Slots =
    {
        new("Front_plate", null, "torso_plate", new string[0], new[] { "Plate_Granit_SAPI_chest" }, true),
        new("Back_plate", null, "torso_plate", new string[0], new[] { "Plate_Granit_SAPI_back" }, true),
        new("Left_side_plate", null, "side_plate", new string[0], new[] { "Plate_Granit_SSAPI_side_left_high" }, true),
        new("Right_side_plate", null, "side_plate", new string[0], new[] { "Plate_Granit_SSAPI_side_right_high" }, true),
        new("Soft_armor_front", null, "soft_panel", new[] { "RibcageUp", "RibcageLow" }, new string[0], false),
        new("Soft_armor_back", null, "soft_panel", new[] { "SpineTop", "SpineDown" }, new string[0], false),
        new("Soft_armor_left", null, "side_panel", new[] { "LeftSideChestDown", "LeftSideChestUp" }, new string[0], false),
        new("soft_armor_right", null, "side_panel", new[] { "RightSideChestDown", "RightSideChestUp" }, new string[0], false),
        new("Collar", null, "collar", new[] { "NeckFront", "NeckBack" }, new string[0], false),
        new("Shoulder_l", null, "shoulder", new[] { "LeftUpperArm" }, new string[0], false),
        new("Shoulder_r", null, "shoulder", new[] { "RightUpperArm" }, new string[0], false),
        new("Groin", null, "groin", new[] { "Pelvis" }, new string[0], false),
        new("Groin_back", null, "groin", new[] { "PelvisBack" }, new string[0], false),
        new("Thigh_l", "cd9b111f3e9a37ded608976d", "thigh", new[] { "LeftThigh" }, new string[0], false),
        new("Thigh_r", "4d383a66105f1ec308a9ad8b", "thigh", new[] { "RightThigh" }, new string[0], false),
        new("Calf_l", "2ce98a56be5196d6f5d86093", "calf", new[] { "LeftCalf" }, new string[0], false),
        new("Calf_r", "7b237e0bd3e555476a8abaa1", "calf", new[] { "RightCalf" }, new string[0], false),
        new("Forearm_l", "fdea2d91986f44d3d50d4ed8", "forearm", new[] { "LeftForearm" }, new string[0], false),
        new("Forearm_r", "31db7f681960be85a7d9322c", "forearm", new[] { "RightForearm" }, new string[0], false),
    };

    public static Piece PieceOf(string key) => Pieces.First(p => p.Key == key);

    /// <summary>Slot name -> piece template id for a full set of class index ci (0 = class 5, 1 = class 6).</summary>
    public static Dictionary<string, string> FullSet(int ci) => Slots.ToDictionary(s => s.Name, s => PieceOf(s.Piece).Ids[ci]);

    public class FbaConfig
    {
        // TEST ONLY: every Scav (assault) wears the carrier with a full set (random class 5 / 6).
        public bool TestScavsWearCarrier { get; set; } = false;
        // PMCs: roll SAIN personality server-side and force it via nickname marker; armor a share of GigaChads.
        public bool GigaChadArmorEnabled { get; set; } = true;
        public double ArmoredGigaChadShare { get; set; } = 0.2;
        public double Class6Share { get; set; } = 0.5;
        // Armored GigaChads fight harder (client side, SAIN): AggressionCoef x ArmoredGigaChadAggression
        // (searches sooner, holds ground longer), full suppression resistance, Wreckless search behaviour.
        public bool ArmoredGigaChadBerserk { get; set; } = true;
        public double ArmoredGigaChadAggression { get; set; } = 2.0;
        // Exoskeletons vs armored gear: true lets that kind of armored item be worn together with any EXO tier.
        public bool ExoAllowArmoredHelmets { get; set; } = false;
        public bool ExoAllowArmoredFaceCovers { get; set; } = false;
        public bool ExoAllowArmoredEyewear { get; set; } = false;
        public bool ExoAllowArmoredRigs { get; set; } = false;
        // Profile allowed to change these from the F12 menu ("" = the first profile that changes one becomes the owner).
        public string SettingsOwnerProfileId { get; set; } = "";
    }

    private static string ConfigPath =>
        System.IO.Path.Combine(System.IO.Path.GetDirectoryName(typeof(FullBodyArmorLoader).Assembly.Location)!, "config.json");

    /// <summary>Writes the current Config back to config.json (F12 changes).</summary>
    public static void SaveConfig()
    {
        var tmp = ConfigPath + ".tmp";
        System.IO.File.WriteAllText(tmp, System.Text.Json.JsonSerializer.Serialize(Config, new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
        System.IO.File.Move(tmp, ConfigPath, true);
    }

    public static FbaConfig Config = new();

    public Task OnLoadAsync(CancellationToken cancellationToken)
    {
        Config = ReadConfig();
        ArmorReady = false;
        MaskReady = false;
        TestModeOn = false;
        ClonedIds.Clear();
        var items = templates.Items;
        if (!items.TryGetValue(new MongoId(RedutT5), out var source) || source?.Properties?.Slots == null)
        {
            logger.Error("[FullBodyArmor] missing Redut-T5 slots; FBA kits disabled");
            return Task.CompletedTask;
        }
        if (!items.TryGetValue(new MongoId(ClonePlate), out var plate) || plate?.Properties == null)
        {
            logger.Error("[FullBodyArmor] missing plate template; FBA kits disabled");
            return Task.CompletedTask;
        }

        var old = source.Properties.Slots.Where(s => s?.Name != null).ToLookup(s => s.Name);
        var slots = new List<Slot>();
        foreach (var cs in Slots)
        {
            var original = old[cs.Name].FirstOrDefault();
            if (cs.Id == null && (original == null || old[cs.Name].Skip(1).Any()))
            {
                logger.Error($"[FullBodyArmor] missing or ambiguous Redut-T5 slot {cs.Name}; FBA kits disabled");
                return Task.CompletedTask;
            }
            var piece = PieceOf(cs.Piece);
            var filter = new HashSet<MongoId>(piece.Ids.Select(i => new MongoId(i)));
            // vanilla torso/side plates stay compatible with the plate slots
            if (cs.PlateColliders.Length > 0 && original?.Properties?.Filters?.FirstOrDefault()?.Filter is { } compatible)
                filter.UnionWith(compatible);
            slots.Add(new Slot
            {
                Id = cs.Id ?? original.Id,
                Name = cs.Name,
                Parent = Carrier,
                Prototype = SlotProto,
                Required = false,
                MergeSlotWithChildren = true,
                Properties = new SlotProperties
                {
                    Filters = new List<SlotFilter>
                    {
                        new()
                        {
                            Filter = filter,
                            Plate = new MongoId(piece.Ids[0]),
                            ArmorColliders = cs.Colliders.ToList(),
                            ArmorPlateColliders = cs.PlateColliders.ToList(),
                            BluntDamageReduceFromSoftArmor = cs.BluntReduce,
                            Locked = false
                        }
                    }
                }
            });
        }

        foreach (var id in Pieces.SelectMany(p => p.Ids).Append(Carrier))
            if (items.ContainsKey(new MongoId(id)))
            {
                logger.Error($"[FullBodyArmor] item ID {id} is already in use; FBA kits disabled");
                return Task.CompletedTask;
            }

        foreach (var piece in Pieces)
            for (int ci = 0; ci < Classes.Length; ci++)
                if (!MakePiece(piece, ci, plate.Parent.ToString())) return Task.CompletedTask;

        var carrier = TryClone(Carrier, new NewItemFromCloneDetails
        {
            NewItemName = string.Empty,
            ItemTplToClone = new MongoId(RedutT5),
            NewId = Carrier,
            ParentId = source.Parent.ToString(),
            HandbookParentId = HbArmor,
            HandbookPriceRoubles = 250000,
            FleaPriceRoubles = 250000,
            Locales = Texts.Item("carrier.name", "carrier.short", "carrier.desc")
        });
        if (carrier == null) return Task.CompletedTask;
        var props = carrier.Properties;
        props.CanSellOnRagfair = false;
        props.Prefab = new Prefab { Path = CarrierBundle, Rcid = "" };
        props.ArmorClass = 0;
        props.ArmorMaterial = ArmorMaterial.Aramid;
        props.Weight = 2.5;
        props.SpeedPenaltyPercent = -3;
        props.WeaponErgonomicPenalty = -2;
        props.MousePenalty = -1;
        props.Slots = slots;

        ArmorReady = true;
        MaskReady = MakeZabeyCopy();
        logger.Success($"[FullBodyArmor] loaded: carrier {Carrier} ({slots.Count} removable slots), {Pieces.Length * Classes.Length} Aramid pieces (classes 5/6)");

        TestModeOn = Config.TestScavsWearCarrier;
        if (TestModeOn) logger.Warning("[FullBodyArmor] TEST MODE: all Scavs get the FBA carrier with a full set (config.json TestScavsWearCarrier)");
        return Task.CompletedTask;
    }

    private FbaConfig ReadConfig()
    {
        var dir = System.IO.Path.GetDirectoryName(typeof(FullBodyArmorLoader).Assembly.Location);
        var path = System.IO.Path.Combine(dir, "config.json");
        if (!System.IO.File.Exists(path)) return new FbaConfig();
        try
        {
            return System.Text.Json.JsonSerializer.Deserialize<FbaConfig>(System.IO.File.ReadAllText(path)) ?? new FbaConfig();
        }
        catch (System.Exception ex)
        {
            logger.Error($"[FullBodyArmor] bad config.json: {ex.Message}");
            return new FbaConfig();
        }
    }


    /// <summary>Lootable copy of Tagilla's welding mask "ZABEY" (the original is Unlootable, Labyrinth boss gear).</summary>
    private bool MakeZabeyCopy()
    {
        var items = templates.Items;
        var src = new MongoId(BossKit.Zabey);
        if (!items.TryGetValue(src, out var source) || source?.Properties == null)
        {
            logger.Warning("[FullBodyArmor] ZABEY mask not in DB; armored GigaChads keep their original head gear");
            return false;
        }
        var hb = templates.Handbook.Items.FirstOrDefault(i => i.Id == src);
        var item = TryClone(BossKit.ZabeyFba, new NewItemFromCloneDetails
        {
            NewItemName = string.Empty,
            ItemTplToClone = src,
            NewId = BossKit.ZabeyFba,
            ParentId = source.Parent.ToString(),
            HandbookParentId = hb?.ParentId.ToString() ?? "5b47574386f77428ca22b331",
            HandbookPriceRoubles = hb?.Price ?? 300000,
            FleaPriceRoubles = hb?.Price ?? 300000,
            Locales = Texts.Item("zabey.name", "zabey.short", "zabey.desc")
        });
        if (item == null) return false;
        var p = item.Properties;
        p.Unlootable = false;
        p.UnlootableFromSide = new List<PlayerSideMask>();
        p.CanSellOnRagfair = false;
        return true;
    }

    private bool MakePiece(Piece pc, int ci, string parent)
    {
        var id = pc.Ids[ci];
        int cls = Classes[ci];
        var item = TryClone(id, new NewItemFromCloneDetails
        {
            NewItemName = string.Empty,
            ItemTplToClone = new MongoId(ClonePlate),
            NewId = id,
            ParentId = parent,
            HandbookParentId = HbPlates,
            HandbookPriceRoubles = cls == 5 ? 60000 : 90000,
            FleaPriceRoubles = cls == 5 ? 60000 : 90000,
            Locales = Texts.Item("piece.name", "piece.short", "piece.desc",
                ("piece", "@piece." + pc.Key), ("short", "@piece." + pc.Key + ".short"), ("cls", cls.ToString()))
        });
        if (item == null) return false;
        var p = item.Properties;
        p.ArmorClass = cls;
        p.ArmorMaterial = ArmorMaterial.Aramid;
        p.MaxDurability = Durability[ci];
        p.Durability = Durability[ci];
        p.ArmorColliders = pc.Colliders.ToList();
        p.ArmorPlateColliders = pc.PlateColliders.ToList();
        p.BluntThroughput = pc.Blunt;
        p.Weight = pc.Weight[ci];
        p.Width = pc.W;
        p.Height = pc.H;
        p.SpeedPenaltyPercent = pc.Speed[ci];
        p.WeaponErgonomicPenalty = pc.Ergo[ci];
        p.MousePenalty = pc.Mouse[ci];
        p.CanSellOnRagfair = false;
        return true;
    }


    private TemplateItem TryClone(string id, NewItemFromCloneDetails details)
    {
        var items = templates.Items;
        var key = new MongoId(id);
        if (items.ContainsKey(key))
        {
            logger.Error($"[FullBodyArmor] cannot clone {id}: item ID is already in use");
            return null;
        }
        try
        {
            var result = customItemService.CreateItemFromClone(details);
            if (result?.Success == true && items.TryGetValue(key, out var item) && item?.Properties != null)
            {
                ClonedIds.Add(key);
                return item;
            }
            logger.Error($"[FullBodyArmor] cannot clone {id}: {string.Join("; ", result?.Errors ?? new List<string>())}");
        }
        catch (System.Exception ex)
        {
            logger.Error($"[FullBodyArmor] cannot clone {id}: {ex.Message}");
        }
        return null;
    }
}
