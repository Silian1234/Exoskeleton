// EXO-2 / EXO-3: slightly lower recoil for the local player (ExoTiers.Recoil: x0.95 / x0.90).
// Scales the per-shot recoil force fed into the new recoil system; weapon stats, sensitivity and dispersion are untouched.
using Comfort.Common;
using EFT;
using EFT.Animations.NewRecoil;
using HarmonyLib;

namespace FullBodyArmorClient
{
    internal static class ExoskeletonRecoil
    {
        internal static void Patch(Harmony harmony)
        {
            var add = AccessTools.DeclaredMethod(typeof(NewRecoilShotEffect), nameof(NewRecoilShotEffect.AddRecoilForce), new[] { typeof(float) })
                      ?? throw new System.MissingMethodException("NewRecoilShotEffect.AddRecoilForce(float)");
            harmony.Patch(add, prefix: new HarmonyMethod(typeof(ExoskeletonRecoil), nameof(ScaleRecoil)));
        }

        private static void ScaleRecoil(NewRecoilShotEffect __instance, ref float __0)
        {
            var player = Singleton<GameWorld>.Instance?.MainPlayer;
            if (player == null || __instance.FirearmController == null || !ReferenceEquals(player.HandsController, __instance.FirearmController)) return;
            __0 *= ExoTiers.Recoil[ExoTiers.Tier(player)];
        }
    }
}
