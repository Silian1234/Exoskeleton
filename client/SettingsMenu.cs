// F12 (BepInEx Configuration Manager) entries for the server-side settings.
// The entries mirror the server: they are filled from the server's values, and a change is sent to the server,
// which accepts it only from the settings owner (config.json SettingsOwnerProfileId; the first profile that
// changes a setting becomes the owner). A refused or failed change is reverted to the server's value.
// What applies when:
//   armored GigaChad switches -> next bot generation (next raid);
//   berserk                   -> bots that spawn after the change;
//   EXO armor rule            -> immediately (client check), the server's item conflicts follow on server restart.
using System;
using BepInEx.Configuration;

namespace FullBodyArmorClient
{
    internal static class SettingsMenu
    {
        private const string Giga = "1. Armored GigaChads", Exo = "2. Exoskeletons";
        private static ConfigEntry<bool> _enabled, _berserk, _helmets, _masks, _glasses, _rigs;
        private static ConfigEntry<float> _share, _class6, _aggression;
        private static bool _syncing, _dirty;
        private static float _changedAt;
        private static string _lastKey;

        internal static void Init(ConfigFile config)
        {
            _enabled = config.Bind(Giga, "Enabled", true, Desc("Some GigaChad PMCs spawn in a full FBA class 5/6 set. Applies from the next raid.", 9));
            _share = config.Bind(Giga, "Share of GigaChads", 0.2f, Desc("Share of GigaChad PMCs that get the armor (0-1). Applies from the next raid.", 8, new AcceptableValueRange<float>(0f, 1f)));
            _class6 = config.Bind(Giga, "Class 6 share", 0.5f, Desc("Share of armored GigaChads in class 6 (the rest are class 5). Applies from the next raid.", 7, new AcceptableValueRange<float>(0f, 1f)));
            _berserk = config.Bind(Giga, "Berserk", true, Desc("Armored GigaChads fight harder: higher SAIN aggression, full suppression resistance, they charge noises. Applies to bots that spawn after the change.", 6));
            _aggression = config.Bind(Giga, "Aggression multiplier", 2f, Desc("SAIN AggressionCoef multiplier for berserk GigaChads: they push sooner and hold ground longer.", 5, new AcceptableValueRange<float>(0.5f, 5f)));
            _helmets = config.Bind(Exo, "Allow armored helmets", false, Desc("Armored helmets can be worn with an exoskeleton. Applies immediately.", 4));
            _masks = config.Bind(Exo, "Allow armored masks", false, Desc("Armored face covers can be worn with an exoskeleton. Applies immediately.", 3));
            _glasses = config.Bind(Exo, "Allow armored glasses", false, Desc("Armored glasses can be worn with an exoskeleton. Applies immediately.", 2));
            _rigs = config.Bind(Exo, "Allow ballistic rigs", false, Desc("Armored rigs can be worn with an exoskeleton. Applies immediately.", 1));

            ServerSettings.Loaded += Show;
            config.SettingChanged += OnChanged;
            Show(ServerSettings.Get());
        }

        private static ConfigDescription Desc(string text, int order, AcceptableValueBase range = null) =>
            new ConfigDescription(text + " Server setting: shared by everyone on this server, only the settings owner can change it.",
                range, new ConfigurationManagerAttributes { Order = order });

        /// <summary>Puts the server's values into the entries without sending them back.</summary>
        private static void Show(FbaSettings s)
        {
            if (_enabled == null || s == null) return;
            _syncing = true;
            try
            {
                _enabled.Value = s.GigaChadArmorEnabled;
                _share.Value = s.ArmoredGigaChadShare;
                _class6.Value = s.Class6Share;
                _berserk.Value = s.ArmoredGigaChadBerserk;
                _aggression.Value = s.ArmoredGigaChadAggression;
                _helmets.Value = s.ExoAllowArmoredHelmets;
                _masks.Value = s.ExoAllowArmoredFaceCovers;
                _glasses.Value = s.ExoAllowArmoredEyewear;
                _rigs.Value = s.ExoAllowArmoredRigs;
            }
            finally { _syncing = false; }
        }

        private static void OnChanged(object sender, SettingChangedEventArgs e)
        {
            if (_syncing || e?.ChangedSetting == null) return;
            var section = e.ChangedSetting.Definition.Section;
            if (section != Giga && section != Exo) return;
            // sliders fire on every step: send once the value has been still for a moment (Tick)
            _dirty = true;
            _changedAt = UnityEngine.Time.realtimeSinceStartup;
            _lastKey = $"{section} / {e.ChangedSetting.Definition.Key} = {e.ChangedSetting.BoxedValue}";
        }

        /// <summary>Called every frame by the plugin.</summary>
        internal static void Tick()
        {
            if (!_dirty || UnityEngine.Time.realtimeSinceStartup - _changedAt < 0.6f) return;
            _dirty = false;
            var wanted = ServerSettings.Get().Copy();
            wanted.GigaChadArmorEnabled = _enabled.Value;
            wanted.ArmoredGigaChadShare = _share.Value;
            wanted.Class6Share = _class6.Value;
            wanted.ArmoredGigaChadBerserk = _berserk.Value;
            wanted.ArmoredGigaChadAggression = _aggression.Value;
            wanted.ExoAllowArmoredHelmets = _helmets.Value;
            wanted.ExoAllowArmoredFaceCovers = _masks.Value;
            wanted.ExoAllowArmoredEyewear = _glasses.Value;
            wanted.ExoAllowArmoredRigs = _rigs.Value;

            var answer = ServerSettings.Update(wanted);
            if (answer == null) { Show(ServerSettings.Get()); return; }
            if (!answer.Accepted)
                Plugin.Log.LogWarning("[FBA-Client] settings change refused by the server: this profile is not the settings owner (config.json SettingsOwnerProfileId)");
            else
            {
                Plugin.ResetBerserk();
                Plugin.Log.LogInfo("[FBA-Client] setting changed on the server: " + _lastKey);
            }
            Show(answer);
        }
    }

    // Read by BepInEx Configuration Manager through reflection (its documented pattern: a class with this name).
    internal sealed class ConfigurationManagerAttributes
    {
        public int? Order;
    }
}
