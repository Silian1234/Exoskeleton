// EXO-3 equipment rule: the suit trades armor for its buffs. It conflicts only with ARMORED gear
// (helmets / face covers / eyewear / rigs that have an armor class or armor inserts); caps, hats, plain
// glasses and unarmored rigs stay allowed. Server side mirrors this in ConflictingItems.
// The server config can allow each gear kind (ExoAllowArmored*), read through ServerSettings; F12 changes apply at once.
// For that the exoskeleton templates' own ConflictingItems (built by the server at start) are emptied on the client
// the first time an exoskeleton is seen, so only this check (which reads the current settings) decides.
//
// Hook: the Slot method that checks equipment conflicts and returns Result<bool> (obfuscated name, resolved by signature).
using System;
using System.Linq;
using System.Reflection;
using EFT;
using EFT.InventoryLogic;
using HarmonyLib;

namespace FullBodyArmorClient
{
    internal static class ExoskeletonEquipment
    {
        internal const string TemplateId = "e5f82a1e0c7846b9a4130de1";   // T1 (all tiers: ExoTiers.Templates)
        private static readonly EquipmentSlot[] ConflictSlots =
        {
            EquipmentSlot.Headwear, EquipmentSlot.TacticalVest, EquipmentSlot.FaceCover, EquipmentSlot.Eyewear
        };

        private static ConstructorInfo _conflictError;   // InventoryError(Item item, Item rootItem, Item conflictingItem)
        private static MethodInfo _toResult;             // implicit Error -> Result<bool>

        internal static bool IsWearing(Player player) => ExoTiers.Tier(player) > 0;

        internal static void Patch(Harmony harmony)
        {
            // Slot.<conflict check>(Item) -> struct Result<bool>  (currently method_4)
            var check = ExoResolve.SingleMethod(typeof(Slot), "slot conflict check", m =>
                ExoResolve.Params(m, typeof(Item)) && m.ReturnType.IsValueType && m.ReturnType.IsGenericType &&
                m.ReturnType.GetGenericArguments()[0] == typeof(bool));
            var resultType = check.ReturnType;

            var errors = typeof(Slot).Assembly.GetTypes()
                .Where(t => typeof(InventoryError).IsAssignableFrom(t) && !t.IsAbstract)
                .SelectMany(t => t.GetConstructors())
                .Where(c => c.GetParameters().Select(p => (p.ParameterType, p.Name))
                    .SequenceEqual(new[] { (typeof(Item), "item"), (typeof(Item), "rootItem"), (typeof(Item), "conflictingItem") }))
                .ToArray();
            if (errors.Length != 1) throw new MissingMethodException($"conflict error type: expected 1, found {errors.Length}");
            _conflictError = errors[0];

            _toResult = resultType.GetMethods(BindingFlags.Static | BindingFlags.Public)
                .FirstOrDefault(m => m.Name == "op_Implicit" && m.ReturnType == resultType &&
                    m.GetParameters().Length == 1 && m.GetParameters()[0].ParameterType.IsAssignableFrom(_conflictError.DeclaringType))
                ?? throw new MissingMethodException(resultType.FullName, "op_Implicit(Error)");

            var hook = typeof(ConflictHook<>).MakeGenericType(resultType).GetMethod(nameof(ConflictHook<bool>.Prefix));
            harmony.Patch(check, prefix: new HarmonyMethod(hook));
            harmony.Patch(AccessTools.PropertyGetter(typeof(Item), nameof(Item.ConflictingItems)),
                postfix: new HarmonyMethod(typeof(ExoskeletonEquipment), nameof(ConflictListPostfix)));
        }

        private static class ConflictHook<TResult>
        {
            public static bool Prefix(Slot __instance, Item __0, ref TResult __result)
            {
                DropNativeList(__0);
                if (__instance.ParentItem is InventoryEquipment eq) DropNativeList(eq.GetSlot(EquipmentSlot.ArmorVest)?.ContainedItem);
                var conflict = FindConflict(__instance, __0);
                if (conflict == null) return true;
                var error = _conflictError.Invoke(new object[] { __0, __instance.ParentItem, conflict });
                __result = (TResult)_toResult.Invoke(null, new[] { error });
                return false;
            }
        }

        private static void ConflictListPostfix(Item __instance, ref string[] __result)
        {
            if (__result == null || __result.Length == 0 || ExoTiers.TierOf(__instance?.StringTemplateId) == 0) return;
            DropNativeList(__instance);
            __result = Array.Empty<string>();
        }

        private static void DropNativeList(Item item)
        {
            if (item == null || ExoTiers.TierOf(item.StringTemplateId) == 0) return;
            var template = item.Template;
            if (template?.ConflictingItems != null && template.ConflictingItems.Length > 0) template.ConflictingItems = Array.Empty<string>();
        }

        private static Item FindConflict(Slot slot, Item incoming)
        {
            if (incoming == null || slot.ParentItem is not InventoryEquipment equipment) return null;
            var vest = equipment.GetSlot(EquipmentSlot.ArmorVest);
            if (ReferenceEquals(slot, vest) && ExoTiers.TierOf(incoming.StringTemplateId) > 0)
            {
                foreach (var slotId in ConflictSlots)
                {
                    if (!Blocked(slotId)) continue;
                    var other = equipment.GetSlot(slotId)?.ContainedItem;
                    if (IsArmored(incoming, other)) return other;
                }
            }
            else if (ExoTiers.TierOf(vest?.ContainedItem?.StringTemplateId) > 0)
            {
                foreach (var slotId in ConflictSlots)
                    if (Blocked(slotId) && ReferenceEquals(slot, equipment.GetSlot(slotId)) && IsArmored(vest.ContainedItem, incoming))
                        return vest.ContainedItem;
            }
            return null;
        }

        /// <summary>False when the server config lets armored gear of this slot be worn with an exoskeleton.</summary>
        private static bool Blocked(EquipmentSlot slot)
        {
            var c = ServerSettings.Get();
            switch (slot)
            {
                case EquipmentSlot.Headwear: return !c.ExoAllowArmoredHelmets;
                case EquipmentSlot.TacticalVest: return !c.ExoAllowArmoredRigs;
                case EquipmentSlot.FaceCover: return !c.ExoAllowArmoredFaceCovers;
                case EquipmentSlot.Eyewear: return !c.ExoAllowArmoredEyewear;
                default: return false;
            }
        }

        /// <summary>True when the item has its own armor class or holds any armor insert/plate.</summary>
        private static bool IsArmored(Item exo, Item other)
        {
            if (other == null) return false;
            if ((other.GetItemComponent<ArmorComponent>()?.ArmorClass ?? 0) > 0) return true;
            if (other is CompoundItem compound)
                foreach (var s in compound.Slots)
                    if ((s?.ContainedItem?.GetItemComponent<ArmorComponent>()?.ArmorClass ?? 0) > 0) return true;
            return false;
        }
    }
}
