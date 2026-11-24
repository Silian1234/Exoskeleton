// Optional compatibility with "PlayerEncumbranceBar" (its own weight bar in the inventory screen).
// That mod recalculates the overweight limits only when the panel is shown, on a strength level-up or on a health effect;
// on an inventory weight change it only moves the current weight. Equipping or removing an exoskeleton changes the
// limits (+15/25/35 kg), so they stayed stale until the screen was reopened. With the mod present, a weight change now
// also refreshes its limits (its UpdateWeightLimits already updates the weight bar itself). Without it nothing happens.
using System;
using HarmonyLib;

namespace FullBodyArmorClient
{
    internal static class EncumbranceBarCompat
    {
        internal static void Patch(Harmony harmony)
        {
            var type = AccessTools.TypeByName("PlayerEncumbranceBar.PlayerEncumbranceBarComponent");
            if (type == null) { Plugin.Log.LogInfo("[Exoskeleton] PlayerEncumbranceBar not installed: no compat needed"); return; }
            var onWeight = AccessTools.DeclaredMethod(type, "OnUpdateWeight");
            var limits = AccessTools.DeclaredMethod(type, "UpdateWeightLimits", new[] { typeof(bool) });
            if (onWeight == null || limits == null) { Plugin.Log.LogWarning("[Exoskeleton] PlayerEncumbranceBar found, but its methods changed: compat skipped"); return; }
            _limits = limits;
            harmony.Patch(onWeight, prefix: new HarmonyMethod(typeof(EncumbranceBarCompat), nameof(Prefix)));
            Plugin.Log.LogInfo("[Exoskeleton] PlayerEncumbranceBar compat: weight limits refresh on equipment change");
        }

        private static System.Reflection.MethodInfo _limits;

        private static bool Prefix(object __instance)
        {
            try { _limits.Invoke(__instance, new object[] { true }); return false; }
            catch (Exception) { return true; }   // fall back to the mod's own behaviour
        }
    }
}
