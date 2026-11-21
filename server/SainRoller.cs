// Server-side replica of SAIN 4.5 personality assignment (PersonalityDictionary.GetPersonality).
// SAIN 4.5 keeps presets on its server mod but still picks the personality on the client, from the preset the
// client loaded. The FBA client therefore POSTs the active preset's assignment table to /fullbodyarmor/sain-assignments
// (on load and on every preset change); it is kept here and saved to sain-assignments.json for server restarts.
//
// SAIN 4.5 order: forced personality (GlobalSettings.Mind.ForcePersonality) -> nickname -> boss -> personalities in
// the preset dictionary's order (first that passes wins) -> PMC fallback: 33% Chad, else Normal.
// A personality passes when Enabled and (random roll of RandomlyAssignedChance, or requirements + chance roll):
//   requirements: role in AllowedTypes, PowerMin < power <= PowerMax, MinLevel < level <= MaxLevel;
//   chance = clamp(MaxChance * r, 0, 100), r = (clamp(power,0,1000) - ScaleStart) / (ScaleEnd - ScaleStart) (InverseScale: 1 - r).
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using SPTarkov.Server.Core.Models.Utils;

namespace FullBodyArmor;

public record SainAssignment
{
    public bool Enabled { get; set; }
    public bool CanBeRandomlyAssigned { get; set; }
    public bool InverseScale { get; set; }
    public double RandomlyAssignedChance { get; set; }
    public double MinLevel { get; set; }
    public double MaxLevel { get; set; }
    public double PowerLevelScaleStart { get; set; }
    public double PowerLevelScaleEnd { get; set; }
    public double PowerLevelMin { get; set; }
    public double PowerLevelMax { get; set; }
    public double MaxChanceIfMeetRequirements { get; set; }
    public List<string> AllowedTypes { get; set; } = new();
}

public record SainPersonality
{
    public string Name { get; set; }
    public int Value { get; set; }
    public SainAssignment Assignment { get; set; }
}

/// <summary>What the FBA client sends: the active SAIN preset's personalities in dictionary order.</summary>
public record SainSnapshot : IRequestData
{
    public string Preset { get; set; }
    public string Forced { get; set; }
    public int ForcedValue { get; set; }
    public List<SainPersonality> Personalities { get; set; } = new();
}

public class SainRoller
{
    public const int GigaChad = 3, Chad = 4, Normal = 8;   // SAIN EPersonality values

    private static readonly object Lock = new();
    private static SainRoller _current;
    private static string _file;

    /// <summary>Roller for the last preset a client reported (null until the first report or a saved file).</summary>
    public static SainRoller Current { get { lock (Lock) return _current; } }

    public SainSnapshot Snapshot { get; }
    private readonly List<(SainPersonality P, HashSet<string> Types)> _order;

    private SainRoller(SainSnapshot s)
    {
        Snapshot = s;
        _order = s.Personalities.Where(p => p?.Assignment != null)
            .Select(p => (p, new HashSet<string>(p.Assignment.AllowedTypes ?? new(), StringComparer.OrdinalIgnoreCase))).ToList();
    }

    /// <summary>Invisible nickname marker: WORD JOINER + 4 bits (EPersonality value) of ZWSP/ZWNJ + WORD JOINER.</summary>
    public static string Marker(int personality)
    {
        var s = "⁠";
        for (int b = 3; b >= 0; b--) s += ((personality >> b) & 1) == 1 ? "‌" : "​";
        return s + "⁠";
    }

    /// <summary>Loads the saved snapshot (if any) from the mod folder.</summary>
    public static string Init(string modDir)
    {
        lock (Lock)
        {
            _file = Path.Combine(modDir, "sain-assignments.json");
            if (!File.Exists(_file)) return null;
            var s = JsonSerializer.Deserialize<SainSnapshot>(File.ReadAllText(_file));
            if (s?.Personalities == null || s.Personalities.Count == 0) return null;
            _current = new SainRoller(s);
            return s.Preset;
        }
    }

    /// <summary>Client report: replaces the roller and saves it. Returns false when it was identical.</summary>
    public static bool Update(SainSnapshot s)
    {
        if (s?.Personalities == null || s.Personalities.Count == 0) throw new InvalidDataException("empty SAIN personality table");
        var json = JsonSerializer.Serialize(s);
        lock (Lock)
        {
            if (_current != null && JsonSerializer.Serialize(_current.Snapshot) == json) return false;
            _current = new SainRoller(s);
            if (_file != null)
            {
                var tmp = _file + ".tmp";
                File.WriteAllText(tmp, json);
                File.Move(tmp, _file, true);
            }
            return true;
        }
    }

    private static bool Chance(Random rng, double percent) => rng.NextDouble() * 100.0 < percent;

    /// <summary>EPersonality value for a bot, same rules as SAIN 4.5 (nickname and boss rules do not apply to PMCs).</summary>
    public int Roll(string role, int level, double power, Random rng)
    {
        if (!string.IsNullOrEmpty(Snapshot.Forced)) return Snapshot.ForcedValue;
        foreach (var (p, types) in _order)
        {
            var a = p.Assignment;
            if (!a.Enabled) continue;
            if (a.CanBeRandomlyAssigned && Chance(rng, a.RandomlyAssignedChance)) return p.Value;
            bool meets = types.Contains(role)
                         && power > a.PowerLevelMin && power <= a.PowerLevelMax
                         && level > a.MinLevel && level <= a.MaxLevel;
            if (!meets) continue;
            var pw = Math.Clamp(power, 0, 1000);
            var r = (pw - a.PowerLevelScaleStart) / (a.PowerLevelScaleEnd - a.PowerLevelScaleStart);
            if (a.InverseScale) r = 1 - r;
            if (Chance(rng, Math.Clamp(a.MaxChanceIfMeetRequirements * r, 0, 100))) return p.Value;
        }
        bool isPmc = role.StartsWith("pmc", StringComparison.OrdinalIgnoreCase);
        return isPmc && Chance(rng, 33) ? Chad : Normal;
    }
}
