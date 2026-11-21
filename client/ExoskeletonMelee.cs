using EFT;
using EFT.InventoryLogic;
using HarmonyLib;

namespace FullBodyArmorClient
{
    internal static class ExoskeletonMelee
    {
        internal static void Patch(Harmony harmony)
        {
            harmony.Patch(AccessTools.DeclaredMethod(typeof(GameWorld), nameof(GameWorld.HackShot),
                new[] { typeof(DamageInfoStruct) }), prefix: new HarmonyMethod(typeof(ExoskeletonMelee), nameof(ScaleKnifeHit)));
        }

        // Both knife strikes construct their own DamageInfoStruct before HackShot.
        private static void ScaleKnifeHit(ref DamageInfoStruct __0)
        {
            if (__0.DamageType != EDamageType.Melee || __0.Weapon?.GetItemComponent<KnifeComponent>() == null) return;
            int tier = ExoTiers.Tier(__0.Player?.iPlayer as Player);
            if (tier > 0) __0.Damage *= ExoTiers.Melee[tier];
        }
    }
}
