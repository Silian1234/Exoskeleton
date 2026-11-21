// EXO tier table (approved by the user 2026-11-21). Index 0 = not wearing an exoskeleton.
using EFT;
using EFT.InventoryLogic;

namespace FullBodyArmorClient
{
    internal static class ExoTiers
    {
        internal static readonly string[] Templates =
        {
            null,
            "e5f82a1e0c7846b9a4130de1",   // T1 EXO-1 construction
            "bfcd6ff9414d8611685db39f",   // T2 EXO-2 military
            "eb8f6601528512fcd0b0fd1d",   // T3 EXO-3 assault
        };

        //                                       none   T1     T2     T3
        internal static readonly float[] Sprint = { 1f, 1.15f, 1.20f, 1.25f };
        internal static readonly float[] Stamina = { 1f, 0.75f, 0.65f, 0.55f };
        internal static readonly float[] Overweight = { 0f, 15f, 25f, 35f };
        internal static readonly float[] Jump = { 1f, 1.25f, 1.35f, 1.45f };      // height multiplier
        internal static readonly float[] Melee = { 1f, 2.0f, 2.5f, 3.0f };
        internal static readonly float[] FallCushion = { 0f, 0.5f, 1.0f, 1.5f };  // metres taken off small falls
        internal static readonly float[] Vault = { 1f, 1.15f, 1.20f, 1.25f };     // only while overweight
        internal static readonly float[] Recoil = { 1f, 1f, 0.95f, 0.90f };       // recoil force multiplier

        internal static int TierOf(string templateId)
        {
            if (templateId == null) return 0;
            for (int i = 1; i < Templates.Length; i++)
                if (Templates[i] == templateId) return i;
            return 0;
        }

        internal static int Tier(Player player) =>
            player == null ? 0 : TierOf(player.Inventory?.Equipment?.GetSlot(EquipmentSlot.ArmorVest)?.ContainedItem?.StringTemplateId);
    }
}
