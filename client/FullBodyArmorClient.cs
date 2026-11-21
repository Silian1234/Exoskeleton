// FullBodyArmor.Client — client/headless BepInEx plugin.
// The server rolls each PMC's SAIN personality and appends an invisible marker to its nickname.
// SAIN 4.4.2 cannot apply it by itself:
//  1) SAIN.BotProfile.NickName is never assigned (always null), so nickname personalities never match;
//  2) setNicknamePersonality uses EPersonality.Normal (8) as "not found", so Normal can't be forced.
// This plugin: fills BotProfile.NickName from the game profile, and in PersonalityDictionary.GetPersonality
// returns the marked personality directly (with its settings), skipping SAIN's random roll.
// Only the equipped FBA carrier and its FBA plates are protected from durability loss.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using BepInEx;
using BepInEx.Logging;
using Comfort.Common;
using EFT;
using EFT.InventoryLogic;
using Fika.Core.Networking.Packets.Player.Common.SubPackets;
using HarmonyLib;
using Newtonsoft.Json;
using Newtonsoft.Json.Converters;
using SAIN.Models.Preset.Personalities;
using SAIN.Preset;
using SAIN.Preset.Personalities;
using SAIN.SAINComponent.Classes.Info;

namespace FullBodyArmorClient
{
    [BepInPlugin("com.silian.exoskeleton.client", "FullBodyArmor Client", "1.0.0")]
    [BepInDependency("me.sol.sain")]
    [BepInDependency("com.fika.core", BepInDependency.DependencyFlags.SoftDependency)]
    public class Plugin : BaseUnityPlugin
    {
        internal static ManualLogSource Log;
        private static readonly EPersonality[] Order =
        {
            EPersonality.Wreckless, EPersonality.SnappingTurtle, EPersonality.GigaChad, EPersonality.Chad,
            EPersonality.Rat, EPersonality.Timmy, EPersonality.Coward, EPersonality.Normal
        };
        private static string[] _markers;
        private static readonly FieldInfo NickField = AccessTools.Field(typeof(BotProfile), nameof(BotProfile.NickName));
        private static FieldInfo _loadedSainPreset;

        private void Awake()
        {
            Log = Logger;
            _markers = Order.Select((n, i) =>
            {
                var s = "\u2060";
                for (int b = 2; b >= 0; b--) s += ((i >> b) & 1) == 1 ? "\u200C" : "\u200B";
                return s + "\u2060";
            }).ToArray();
            var h = new Harmony("com.silian.exoskeleton.client");
            // EXO-3: every feature resolves its game members at runtime and is hooked independently;
            // a failed lookup disables only that feature and is logged as "[Exoskeleton] <feature>: DISABLED".
            var exo = new Harmony("com.silian.exoskeleton.exo");
            void Feature(string name, Action<Harmony> patch)
            {
                try { patch(exo); Log.LogInfo($"[Exoskeleton] {name}: hooked"); }
                catch (Exception ex) { Log.LogError($"[Exoskeleton] {name}: DISABLED — {ex.Message}"); }
            }
            Feature("equipment rule", ExoskeletonEquipment.Patch);
            Feature("melee", ExoskeletonMelee.Patch);
            Feature("recoil", ExoskeletonRecoil.Patch);
            ExoskeletonMovement.Patch(exo);
            ExoskeletonTraversal.Patch(new Harmony("com.silian.exoskeleton.traversal"));
            foreach (var ctor in AccessTools.GetDeclaredConstructors(typeof(BotProfile)))
                h.Patch(ctor, postfix: new HarmonyMethod(typeof(Plugin), nameof(ProfileCtorPost)));
            h.Patch(AccessTools.Method(typeof(PersonalityDictionary), nameof(PersonalityDictionary.GetPersonality)),
                prefix: new HarmonyMethod(typeof(Plugin), nameof(GetPersonalityPre)));
            Log.LogInfo("[FBA-Client] SAIN patched: BotProfile.NickName fill + marker personalities");
            EnablePresetExport(h);

            h.Patch(AccessTools.Method(typeof(ArmorComponent), nameof(ArmorComponent.ApplyDurabilityDamage)),
                prefix: new HarmonyMethod(typeof(Plugin), nameof(DurabilityPre)));
            var fikaPlayer = AccessTools.TypeByName("Fika.Core.Main.Players.FikaPlayer");
            bool fikaPatched = false;
            if (fikaPlayer != null)
                try { fikaPatched = PatchFika(h, fikaPlayer); }
                catch (Exception ex) { Log.LogWarning("[FBA-Client] Fika durability sync left untouched: " + ex.Message); }
            Log.LogInfo("[FBA-Client] FBA carrier and plate durability lock" + (fikaPatched ? " (+Fika packets)" : ""));
        }

        // Keep the Fika type references out of the standalone game's startup path.
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static bool PatchFika(Harmony harmony, Type fikaPlayer)
        {
            var handle = AccessTools.Method(fikaPlayer, "HandleArmorDamagePacket", new[] { typeof(ArmorDamagePacket) });
            if (handle == null || AccessTools.Field(typeof(ArmorDamagePacket), "ItemId")?.FieldType != typeof(MongoID))
                throw new MissingMethodException("unsupported armor packet format");
            harmony.Patch(handle, prefix: new HarmonyMethod(typeof(FikaDurabilityHooks), nameof(FikaDurabilityHooks.Prefix)));
            return true;
        }

        private const string FbaCarrier = "554bc0fb5531ccd849af6506";
        private static readonly HashSet<string> FbaPlates = new HashSet<string>(StringComparer.Ordinal)
        {
            "82b4d27429a5fd99399fb6fa", "6fefd5b26ac335d567ca9755",
            "14b50cfc05885d875c6632c4", "0846039c668ce23e8f2a1992",
            "d27af43d3b5456d1ee0fd111", "737c907f2c27da36b11a70d4",
            "703e4553c54eaf41ca4503a8", "577eb8a472a4e809df0da032",
            "5cfbda438d0b92eb94e81f91", "1fa7cf9c7bb8348898a330b5",
            "c030573bc7e880359da2d8c4", "3ef4c409bedad277d84fc355",
            "4abe324c2efd90acc907796a", "759310ddb641a69611156e75",
            "f950b3b94783702f8134fc3d", "c465a652415dc5cfe9b1fa6e",
            "354274b72104b70253a56df3", "b48cfef239dab289b7e6d452",
            "59d089a23a0a45c761490fa2", "9bdce17575648290edd39b91"
        };

        private static Item GetProtectedCarrier(Player p)
        {
            if (p == null || p.HealthController == null || !p.HealthController.IsAlive) return null;
            var nick = p.Profile?.Nickname;
            if (nick == null || !nick.Contains(_markers[2])) return null; // index 2 = GigaChad
            var vest = p.Inventory?.Equipment?.GetSlot(EquipmentSlot.ArmorVest)?.ContainedItem;
            return vest?.StringTemplateId == FbaCarrier ? vest : null;
        }

        private static bool IsProtectedPiece(Item item, Item carrier) =>
            carrier != null && item != null && (item.Id == carrier.Id ||
                (FbaPlates.Contains(item.StringTemplateId) && item.Parent?.Container?.ParentItem?.Id == carrier.Id));

        private static bool DurabilityPre(ArmorComponent __instance)
        {
            try
            {
                var item = __instance?.Item;
                var tpl = item?.StringTemplateId;
                if (tpl == null || (tpl != FbaCarrier && !FbaPlates.Contains(tpl))) return true;
                var owner = item.Owner as TraderControllerClass;
                if (owner == null) return true;
                var p = Singleton<GameWorld>.Instance?.GetAlivePlayerByProfileID(owner.ID);
                return !IsProtectedPiece(item, GetProtectedCarrier(p));
            }
            catch { return true; }
        }

        private static class FikaDurabilityHooks
        {
            internal static bool Prefix(Player __instance, ArmorDamagePacket __0)
            {
                try
                {
                    var carrier = GetProtectedCarrier(__instance);
                    if (carrier == null) return true;
                    string id = __0.ItemId;
                    if (carrier.Id == id) return false;
                    if (carrier is CompoundItem compound)
                        foreach (var slot in compound.Slots)
                        {
                            var item = slot?.ContainedItem;
                            if (item?.Id == id) return !IsProtectedPiece(item, carrier);
                        }
                    return true;
                }
                catch { return true; }
            }
        }

        private static void EnablePresetExport(Harmony harmony)
        {
            try
            {
                var handler = typeof(SAINPresetClass).Assembly.GetType("SAIN.Plugin.PresetHandler");
                var update = handler == null ? null : AccessTools.Method(handler, "UpdateExistingBots");
                _loadedSainPreset = handler == null ? null : AccessTools.Field(handler, "LoadedPreset");
                if (update == null || _loadedSainPreset == null)
                {
                    Log.LogWarning("[FBA-Client] SAIN built-in preset export unavailable");
                    return;
                }
                harmony.Patch(update, postfix: new HarmonyMethod(typeof(Plugin), nameof(ExportBuiltinPreset)));
                ExportBuiltinPreset();
            }
            catch (Exception ex) { Log.LogWarning("[FBA-Client] SAIN preset export hook failed: " + ex.Message); }
        }

        private static void ExportBuiltinPreset()
        {
            try
            {
                var preset = _loadedSainPreset?.GetValue(null) as SAINPresetClass;
                if (preset?.Info == null || preset.Info.IsCustom) return;
                var dictionary = preset.PersonalityManager.PersonalityDictionary;
                var snapshot = new
                {
                    Preset = preset.Info.BaseSAINDifficulty.ToString(),
                    Assignments = Order.ToDictionary(p => p.ToString(), p => dictionary[p].Assignment)
                };
                var dir = Path.Combine(Path.GetDirectoryName(typeof(SAINPresetClass).Assembly.Location), "Presets");
                var path = Path.Combine(dir, "fba-built-in-assignments.json");
                var data = JsonConvert.SerializeObject(snapshot, new StringEnumConverter());
                var temp = path + ".tmp";
                File.WriteAllText(temp, data);
                if (File.Exists(path)) File.Replace(temp, path, null);
                else File.Move(temp, path);
            }
            catch (Exception ex) { Log.LogWarning("[FBA-Client] SAIN preset export failed: " + ex.Message); }
        }

        private static void ProfileCtorPost(BotProfile __instance)
        {
            try
            {
                // NickName is a readonly field that SAIN never initialises -> set via reflection
                if (string.IsNullOrEmpty(__instance.NickName))
                    NickField.SetValue(__instance, __instance.BotOwner?.Profile?.Nickname);
            }
            catch (Exception ex) { Log.LogWarning("[FBA-Client] nickname fill failed: " + ex.Message); }
        }

        private static bool GetPersonalityPre(PersonalityDictionary __instance, SAINBotInfoClass infoClass,
            ref PersonalitySettingsClass settings, ref EPersonality __result)
        {
            try
            {
                var nick = infoClass?.Profile?.BotOwner?.Profile?.Nickname;
                if (string.IsNullOrEmpty(nick)) return true;
                for (int i = 0; i < _markers.Length; i++)
                {
                    if (!nick.Contains(_markers[i])) continue;
                    if (!__instance.TryGetValue(Order[i], out var s)) return true;
                    settings = s;
                    __result = Order[i];
                    return false;
                }
            }
            catch (Exception ex) { Log.LogWarning("[FBA-Client] marker personality failed: " + ex.Message); }
            return true;
        }
    }
}
