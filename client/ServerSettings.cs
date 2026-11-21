// Switches from the server mod's config.json: read from /fullbodyarmor/settings, changed through
// /fullbodyarmor/settings/update (F12 menu, see SettingsMenu). The server is the source of truth: only the
// settings owner may change them, and every Fika client / the headless client follows the host server's values.
// Until the server answers (or with an older server mod without these routes) the defaults below apply:
// they match the server defaults, so the client never allows more than the server does.
using System;
using Newtonsoft.Json;
using SPT.Common.Http;

namespace FullBodyArmorClient
{
    internal sealed class FbaSettings
    {
        public bool GigaChadArmorEnabled = true;
        public float ArmoredGigaChadShare = 0.2f;
        public float Class6Share = 0.5f;
        public bool ArmoredGigaChadBerserk = true;
        public float ArmoredGigaChadAggression = 2f;
        public bool ExoAllowArmoredHelmets;
        public bool ExoAllowArmoredFaceCovers;
        public bool ExoAllowArmoredEyewear;
        public bool ExoAllowArmoredRigs;
        // server answer only
        public bool CanEdit;
        public bool Accepted;

        internal FbaSettings Copy() => (FbaSettings)MemberwiseClone();
    }

    internal static class ServerSettings
    {
        private static readonly FbaSettings Defaults = new FbaSettings();
        private static FbaSettings _loaded;
        private static DateTime _nextTry;
        private static bool _warned;

        /// <summary>Raised (on the calling thread) whenever the server's values are (re)loaded.</summary>
        internal static event Action<FbaSettings> Loaded;

        internal static FbaSettings Get()
        {
            if (_loaded != null) return _loaded;
            if (DateTime.UtcNow < _nextTry) return Defaults;
            try
            {
                var json = RequestHandler.GetJson("/fullbodyarmor/settings");
                if (string.IsNullOrEmpty(json)) throw new InvalidOperationException("empty answer (server mod older than 1.1.0?)");
                Set(JsonConvert.DeserializeObject<FbaSettings>(json) ?? throw new InvalidOperationException("bad answer"));
                Plugin.Log.LogInfo("[FBA-Client] server settings: " + JsonConvert.SerializeObject(_loaded));
                return _loaded;
            }
            catch (Exception ex)
            {
                _nextTry = DateTime.UtcNow.AddSeconds(30);
                if (!_warned) Plugin.Log.LogWarning("[FBA-Client] server settings unavailable, using defaults: " + ex.Message);
                _warned = true;
                return Defaults;
            }
        }

        /// <summary>Sends new values to the server; returns what the server holds afterwards (null when unreachable).</summary>
        internal static FbaSettings Update(FbaSettings wanted)
        {
            try
            {
                var json = RequestHandler.PostJson("/fullbodyarmor/settings/update", JsonConvert.SerializeObject(wanted));
                var answer = JsonConvert.DeserializeObject<FbaSettings>(json) ?? throw new InvalidOperationException("bad answer");
                Set(answer);
                return answer;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[FBA-Client] settings update failed: " + ex.Message);
                return null;
            }
        }

        private static void Set(FbaSettings s)
        {
            _loaded = s;
            Loaded?.Invoke(s);
        }
    }
}
