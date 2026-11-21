// Settings shared with the FBA client plugin (BepInEx F12 menu).
//   /fullbodyarmor/settings        -> current switches (+ whether this profile may change them)
//   /fullbodyarmor/settings/update -> change them; accepted only from the settings owner, then saved to config.json
//   /fullbodyarmor/sain-assignments -> the client's active SAIN personality table (see SainRoller)
// Owner: config.json SettingsOwnerProfileId. Empty = the first profile that changes a setting becomes the owner
// (single player: you; Fika: whoever changes a setting first, normally the host). Other profiles are refused.
// Fika clients and the headless client read the switches from the host server, so every player follows one config.
using System.Threading.Tasks;
using SPTarkov.DI.Annotations;
using SPTarkov.Server.Core.DI;
using SPTarkov.Server.Core.Models.Utils;
using SPTarkov.Server.Core.Utils;
using SPTarkov.Common.Models.Logging;

namespace FullBodyArmor;

public record FbaClientSettings : IRequestData
{
    public bool GigaChadArmorEnabled { get; set; }
    public double ArmoredGigaChadShare { get; set; }
    public double Class6Share { get; set; }
    public bool ArmoredGigaChadBerserk { get; set; }
    public double ArmoredGigaChadAggression { get; set; }
    public bool ExoAllowArmoredHelmets { get; set; }
    public bool ExoAllowArmoredFaceCovers { get; set; }
    public bool ExoAllowArmoredEyewear { get; set; }
    public bool ExoAllowArmoredRigs { get; set; }
    // answer only
    public bool CanEdit { get; set; }
    public bool Accepted { get; set; }
}

[Injectable]
public class ClientSettingsRouter(JsonUtil json, ISptLogger<ClientSettingsRouter> log) : StaticRouter(json,
[
    new RouteAction("/fullbodyarmor/settings", (url, info, sessionId, output, cancellationToken) =>
        new ValueTask<object>(json.Serialize(Current(sessionId.ToString(), false)))),

    new RouteAction<FbaClientSettings>("/fullbodyarmor/settings/update", (url, info, sessionId, output, cancellationToken) =>
    {
        var id = sessionId.ToString();
        var c = FullBodyArmorLoader.Config;
        lock (c)
        {
            if (!string.IsNullOrEmpty(c.SettingsOwnerProfileId) && c.SettingsOwnerProfileId != id)
            {
                log.Warning($"[FullBodyArmor] settings change from profile {id} refused: owner is {c.SettingsOwnerProfileId} (config.json SettingsOwnerProfileId)");
                return new ValueTask<string>(json.Serialize(Current(id, false)));
            }
            if (string.IsNullOrEmpty(c.SettingsOwnerProfileId))
            {
                c.SettingsOwnerProfileId = id;
                log.Info($"[FullBodyArmor] profile {id} is now the settings owner");
            }
            c.GigaChadArmorEnabled = info.GigaChadArmorEnabled;
            c.ArmoredGigaChadShare = System.Math.Clamp(info.ArmoredGigaChadShare, 0, 1);
            c.Class6Share = System.Math.Clamp(info.Class6Share, 0, 1);
            c.ArmoredGigaChadBerserk = info.ArmoredGigaChadBerserk;
            c.ArmoredGigaChadAggression = System.Math.Clamp(info.ArmoredGigaChadAggression, 0.1, 10);
            c.ExoAllowArmoredHelmets = info.ExoAllowArmoredHelmets;
            c.ExoAllowArmoredFaceCovers = info.ExoAllowArmoredFaceCovers;
            c.ExoAllowArmoredEyewear = info.ExoAllowArmoredEyewear;
            c.ExoAllowArmoredRigs = info.ExoAllowArmoredRigs;
            FullBodyArmorLoader.SaveConfig();
        }
        log.Info($"[FullBodyArmor] settings changed from F12: armored GigaChads {(c.GigaChadArmorEnabled ? "on" : "off")} " +
            $"{c.ArmoredGigaChadShare:P0} (class 6 {c.Class6Share:P0}), berserk {(c.ArmoredGigaChadBerserk ? "on" : "off")} x{c.ArmoredGigaChadAggression}, " +
            $"EXO allows helmets {c.ExoAllowArmoredHelmets}, masks {c.ExoAllowArmoredFaceCovers}, glasses {c.ExoAllowArmoredEyewear}, rigs {c.ExoAllowArmoredRigs}");
        return new ValueTask<string>(json.Serialize(Current(id, true)));
    }),

    new RouteAction<SainSnapshot>("/fullbodyarmor/sain-assignments", (url, info, sessionId, output, cancellationToken) =>
    {
        if (SainRoller.Update(info))
            log.Success($"[FullBodyArmor] SAIN personalities from client: preset {info.Preset}, {info.Personalities.Count} personalities" +
                (string.IsNullOrEmpty(info.Forced) ? "" : $", forced {info.Forced}"));
        return new ValueTask<string>("{}");
    })
])
{
    private static FbaClientSettings Current(string profileId, bool accepted)
    {
        var c = FullBodyArmorLoader.Config;
        return new FbaClientSettings
        {
            GigaChadArmorEnabled = c.GigaChadArmorEnabled,
            ArmoredGigaChadShare = c.ArmoredGigaChadShare,
            Class6Share = c.Class6Share,
            ArmoredGigaChadBerserk = c.ArmoredGigaChadBerserk,
            ArmoredGigaChadAggression = c.ArmoredGigaChadAggression,
            ExoAllowArmoredHelmets = c.ExoAllowArmoredHelmets,
            ExoAllowArmoredFaceCovers = c.ExoAllowArmoredFaceCovers,
            ExoAllowArmoredEyewear = c.ExoAllowArmoredEyewear,
            ExoAllowArmoredRigs = c.ExoAllowArmoredRigs,
            CanEdit = string.IsNullOrEmpty(c.SettingsOwnerProfileId) || c.SettingsOwnerProfileId == profileId,
            Accepted = accepted,
        };
    }
}
