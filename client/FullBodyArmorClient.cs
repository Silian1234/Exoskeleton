// FullBodyArmor.Client — client/headless BepInEx plugin.
// The server rolls each PMC's SAIN personality and appends an invisible marker to its nickname.
// SAIN (4.4.2 and still 4.5.1) cannot apply it by itself:
//  1) SAIN.BotProfile.NickName is never assigned (always null), so nickname personalities never match;
//  2) setNicknamePersonality uses EPersonality.Normal (8) as "not found", so Normal can't be forced.
// This plugin: fills BotProfile.NickName from the game profile, and in PersonalityDictionary.GetPersonality
// returns the marked personality directly (with its settings), skipping SAIN's random roll.
// SAIN 4.5 picks personalities on the client from the loaded preset, so this plugin reports the preset's
// personality table to the server (/fullbodyarmor/sain-assignments) whenever SAIN loads or changes a preset.
// Only the equipped FBA carrier and its FBA plates are protected from durability loss.
// Armored GigaChads (marker GigaChad + FBA carrier) get a harder-fighting copy of the GigaChad settings (Berserk).
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
using SPT.Common.Http;
using SAIN.Preset.Shared.Models.Preset.Personalities;
using SAIN.Preset.Shared.Personalities.BasePersonality;
using Newtonsoft.Json;
using Newtonsoft.Json.Converters;
using SAIN.Models.Preset.Personalities;
using SAIN.Preset;
using SAIN.Preset.Personalities;
using SAIN.SAINComponent.Classes.Info;

namespace FullBodyArmorClient
{
    [BepInPlugin("com.silian.exoskeleton.client", "FullBodyArmor Client", "1.1.1")]
    [BepInDependency("me.sol.sain")]
    [BepInDependency("com.fika.core", BepInDependency.DependencyFlags.SoftDependency)]
    [BepInDependency("com.mpstark.PlayerEncumbranceBar", BepInDependency.DependencyFlags.SoftDependency)]
    public class Plugin : BaseUnityPlugin
    {
        internal static ManualLogSource Log;
        // nickname marker: WORD JOINER + 4 bits (EPersonality value, ZWNJ = 1, ZWSP = 0) + WORD JOINER
        private const char MarkEdge = '\u2060', Bit1 = '\u200C', Bit0 = '\u200B';
        private static readonly char[] MarkerChars = { MarkEdge, Bit0, Bit1 };
        private static readonly FieldInfo NickField = AccessTools.Field(typeof(BotProfile), nameof(BotProfile.NickName));
        private static FieldInfo _loadedSainPreset;

        private void Awake()
        {
            Log = Logger;
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
            try { EncumbranceBarCompat.Patch(exo); } catch (Exception ex) { Log.LogWarning("[Exoskeleton] PlayerEncumbranceBar compat failed: " + ex.Message); }
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
            SettingsMenu.Init(Config);
        }

        private void Update() => SettingsMenu.Tick();

        /// <summary>Drops the berserk copies so bots spawned after a settings change use the new values.</summary>
        internal static void ResetBerserk() => BerserkCache = new ConditionalWeakTable<PersonalitySettingsClass, PersonalitySettingsClass>();

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
            if (Decode(nick) != (int)EPersonality.GigaChad) return null;
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
                var owner = item.Owner as ItemController;
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

        /// <summary>EPersonality value of the server's nickname marker, or -1.</summary>
        private static int Decode(string nick)
        {
            if (string.IsNullOrEmpty(nick)) return -1;
            for (int i = nick.IndexOf(MarkEdge); i >= 0 && i + 5 < nick.Length; i = nick.IndexOf(MarkEdge, i + 1))
            {
                if (nick[i + 5] != MarkEdge) continue;
                int v = 0; bool ok = true;
                for (int k = 1; k <= 4 && ok; k++)
                {
                    var c = nick[i + k];
                    if (c == Bit1) v = v * 2 + 1; else if (c == Bit0) v *= 2; else ok = false;
                }
                if (ok) return v;
            }
            return -1;
        }

        private static string _lastReport;

        private static void EnablePresetExport(Harmony harmony)
        {
            try
            {
                var handler = typeof(SAINPresetClass).Assembly.GetType("SAIN.Plugin.PresetHandler");
                _loadedSainPreset = handler == null ? null : AccessTools.Field(handler, "LoadedPreset");
                if (_loadedSainPreset == null)
                {
                    Log.LogWarning("[FBA-Client] SAIN preset report unavailable (PresetHandler.LoadedPreset not found)");
                    return;
                }
                var hooked = new List<string>();
                foreach (var name in new[] { "UpdateExistingBots", "InitPresetFromDefinition", "loadDefault" })
                {
                    var m = AccessTools.Method(handler, name);
                    if (m == null) continue;
                    harmony.Patch(m, postfix: new HarmonyMethod(typeof(Plugin), nameof(ReportPreset)));
                    hooked.Add(name);
                }
                Log.LogInfo("[FBA-Client] SAIN preset report hooks: " + string.Join(", ", hooked));
                ReportPreset();
            }
            catch (Exception ex) { Log.LogWarning("[FBA-Client] SAIN preset report hook failed: " + ex.Message); }
        }

        /// <summary>Sends the loaded SAIN preset's personality table (dictionary order) to the server's SainRoller.</summary>
        private static void ReportPreset()
        {
            try
            {
                var preset = _loadedSainPreset?.GetValue(null) as SAINPresetClass;
                var dictionary = preset?.PersonalityManager?.PersonalityDictionary;
                if (preset?.Info == null || dictionary == null || dictionary.Count == 0) return;
                var forced = preset.GlobalSettings?.Mind?.ForcePersonality?.Where(kv => kv.Value).Select(kv => (EPersonality?)kv.Key).FirstOrDefault();
                var name = preset.Info.Name;
                var personalities = dictionary.Select(kv => new { Name = kv.Key.ToString(), Value = (int)kv.Key, kv.Value?.Assignment }).ToList();
                var json = JsonConvert.SerializeObject(new
                {
                    Preset = name,
                    Forced = forced?.ToString(),
                    ForcedValue = (int)(forced ?? 0),
                    Personalities = personalities
                }, new StringEnumConverter());
                if (json == _lastReport) return;
                _lastReport = json;
                System.Threading.Tasks.Task.Run(() =>
                {
                    try
                    {
                        RequestHandler.PostJson("/fullbodyarmor/sain-assignments", json);
                        Log.LogInfo($"[FBA-Client] SAIN preset reported to server: {name}, {personalities.Count} personalities" +
                            (forced == null ? "" : $", forced {forced}"));
                    }
                    catch (Exception ex) { _lastReport = null; Log.LogWarning("[FBA-Client] SAIN preset report failed: " + ex.Message); }
                });
            }
            catch (Exception ex) { Log.LogWarning("[FBA-Client] SAIN preset report failed: " + ex.Message); }
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

        private static readonly MethodInfo CloneMethod =
            typeof(object).GetMethod("MemberwiseClone", BindingFlags.Instance | BindingFlags.NonPublic);
        private static ConditionalWeakTable<PersonalitySettingsClass, PersonalitySettingsClass> BerserkCache =
            new ConditionalWeakTable<PersonalitySettingsClass, PersonalitySettingsClass>();


        private static T Clone<T>(T o) where T : class => o == null ? null : (T)CloneMethod.Invoke(o, null);

        private static bool WearsFbaCarrier(SAINBotInfoClass info) =>
            info?.Profile?.BotOwner?.Profile?.Inventory?.Equipment?.GetSlot(EquipmentSlot.ArmorVest)?.ContainedItem?.StringTemplateId == FbaCarrier;

        /// <summary>
        /// Armored GigaChad: a copy of the active GigaChad settings with AggressionCoef x ArmoredGigaChadAggression
        /// (SAIN: search starts sooner, ground is held longer), full suppression resistance (SAIN averages it with the
        /// bot-type value) and the Wreckless search block (charges noises, short search wait, sprints while searching).
        /// One copy per preset object, so preset reloads are picked up. The original settings are never modified.
        /// </summary>
        private static PersonalitySettingsClass Berserk(PersonalityDictionary dict, PersonalitySettingsClass giga, string nick)
        {
            var cfg = ServerSettings.Get();
            if (!cfg.ArmoredGigaChadBerserk || giga?.Behavior?.General == null || giga.Difficulty == null) return giga;
            if (!BerserkCache.TryGetValue(giga, out var b))
            {
                b = Clone(giga);
                b.Behavior = Clone(giga.Behavior);
                b.Behavior.General = Clone(giga.Behavior.General);
                b.Behavior.General.SuppressionResistance = 1f;
                b.Difficulty = Clone(giga.Difficulty);
                b.Difficulty.AggressionCoef *= Math.Max(0.1f, cfg.ArmoredGigaChadAggression);
                if (dict.TryGetValue(EPersonality.Wreckless, out var w) && w?.Behavior?.Search != null)
                    b.Behavior.Search = w.Behavior.Search;
                BerserkCache.Add(giga, b);
                Log.LogInfo($"[FBA-Client] armored GigaChad berserk settings: AggressionCoef {giga.Difficulty.AggressionCoef} -> {b.Difficulty.AggressionCoef}, " +
                    $"SuppressionResistance 1, search {b.Behavior.Search?.HeardFromPeaceBehavior}");
            }
            Log.LogInfo("[FBA-Client] armored GigaChad berserk: " + nick.Trim(MarkerChars));
            return b;
        }

        private static bool GetPersonalityPre(PersonalityDictionary __instance, SAINBotInfoClass infoClass,
            ref PersonalitySettingsClass settings, ref EPersonality __result)
        {
            try
            {
                var nick = infoClass?.Profile?.BotOwner?.Profile?.Nickname;
                var v = Decode(nick);
                if (v < 0) return true;
                var personality = (EPersonality)v;
                if (!__instance.TryGetValue(personality, out var s)) return true;
                if (personality == EPersonality.GigaChad && WearsFbaCarrier(infoClass)) s = Berserk(__instance, s, nick);
                settings = s;
                __result = personality;
                return false;
            }
            catch (Exception ex) { Log.LogWarning("[FBA-Client] marker personality failed: " + ex.Message); }
            return true;
        }
    }
}
