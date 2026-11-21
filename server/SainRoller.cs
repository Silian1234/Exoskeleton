// Server-side replica of SAIN 4.3 personality assignment (PersonalityDictionary.GetPersonality),
// read from the client's active SAIN preset so it always matches the game.
// Order = Enum.GetValues(EPersonality); first personality that passes wins; PMC fallback: 33% Chad else Normal.
// chance = clamp(MaxChance * r, 0, 100), r = (clamp(power,0,1000) - ScaleStart) / (ScaleEnd - ScaleStart) (InverseScale: 1 - r).
// Requirements: role in AllowedTypes, PowerMin < power <= PowerMax, MinLevel < level <= MaxLevel.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace FullBodyArmor;

public class SainRoller
{
    public static readonly string[] Order = { "Wreckless", "SnappingTurtle", "GigaChad", "Chad", "Rat", "Timmy", "Coward", "Normal" };
    public static readonly Dictionary<string, int> EnumValue = new()
    {
        ["Wreckless"] = 1, ["SnappingTurtle"] = 2, ["GigaChad"] = 3, ["Chad"] = 4,
        ["Rat"] = 5, ["Timmy"] = 6, ["Coward"] = 7, ["Normal"] = 8
    };

    /// <summary>Invisible nickname marker per personality: WORD JOINER + 3 bits of ZWSP/ZWNJ + WORD JOINER.</summary>
    public static string Marker(string personality)
    {
        int i = Array.IndexOf(Order, personality);
        var s = "\u2060";
        for (int b = 2; b >= 0; b--) s += ((i >> b) & 1) == 1 ? "\u200C" : "\u200B";
        return s + "\u2060";
    }

    private class A
    {
        public bool Enabled, CanBeRandomlyAssigned, InverseScale;
        public double RandomlyAssignedChance, MinLevel, MaxLevel, PowerLevelScaleStart, PowerLevelScaleEnd, PowerLevelMin, PowerLevelMax, MaxChance;
        public HashSet<string> AllowedTypes = new(StringComparer.OrdinalIgnoreCase);
    }

    private readonly Dictionary<string, A> _p = new();
    private SainRoller() { }

    public static SainRoller Load(string sainPluginDir, out string source)
    {
        var roller = new SainRoller();
        var presets = Path.Combine(sainPluginDir, "Presets");
        using var cfg = JsonDocument.Parse(File.ReadAllText(Path.Combine(presets, "ConfigSettings.json")));
        var custom = cfg.RootElement.GetProperty("SelectedCustomPreset").GetString();
        if (!string.IsNullOrWhiteSpace(custom) && !custom.Equals("none", StringComparison.OrdinalIgnoreCase))
        {
            source = Path.Combine(presets, custom, "Personalities");
            foreach (var name in Order)
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(source, name + ".json")));
                roller.ReadAssignment(name, doc.RootElement.GetProperty("Assignment"));
            }
            return roller;
        }

        var selected = cfg.RootElement.GetProperty("SelectedDefaultPreset").GetString();
        var preset = string.IsNullOrWhiteSpace(selected) || selected == "none" ? "hard" : selected;
        var path = Path.Combine(presets, "fba-built-in-assignments.json");
        if (!File.Exists(path) || File.GetLastWriteTimeUtc(path) < File.GetLastWriteTimeUtc(Path.Combine(sainPluginDir, "SAIN.dll")))
            throw new IOException($"waiting for the FBA client to export SAIN built-in preset {preset}");
        using var snapshot = JsonDocument.Parse(File.ReadAllText(path));
        if (!preset.Equals(snapshot.RootElement.GetProperty("Preset").GetString(), StringComparison.OrdinalIgnoreCase))
            throw new IOException($"waiting for the FBA client to export SAIN built-in preset {preset}");
        var assignments = snapshot.RootElement.GetProperty("Assignments");
        foreach (var name in Order)
            roller.ReadAssignment(name, assignments.GetProperty(name));
        source = $"SAIN built-in preset {preset}";
        return roller;
    }

    private void ReadAssignment(string name, JsonElement a)
    {
        var x = new A
        {
                Enabled = a.GetProperty("Enabled").GetBoolean(),
                CanBeRandomlyAssigned = a.GetProperty("CanBeRandomlyAssigned").GetBoolean(),
                InverseScale = a.TryGetProperty("InverseScale", out var inv) && inv.GetBoolean(),
                RandomlyAssignedChance = a.GetProperty("RandomlyAssignedChance").GetDouble(),
                MinLevel = a.GetProperty("MinLevel").GetDouble(),
                MaxLevel = a.GetProperty("MaxLevel").GetDouble(),
                PowerLevelScaleStart = a.GetProperty("PowerLevelScaleStart").GetDouble(),
                PowerLevelScaleEnd = a.GetProperty("PowerLevelScaleEnd").GetDouble(),
                PowerLevelMin = a.GetProperty("PowerLevelMin").GetDouble(),
                PowerLevelMax = a.GetProperty("PowerLevelMax").GetDouble(),
                MaxChance = a.GetProperty("MaxChanceIfMeetRequirements").GetDouble(),
        };
        if (a.TryGetProperty("AllowedTypes", out var at))
            foreach (var t in at.EnumerateArray()) x.AllowedTypes.Add(t.ToString());
        _p[name] = x;
    }

    private static bool Roll(Random rng, double percent) => rng.NextDouble() * 100.0 < percent;

    public string Roll(string role, int level, double power, Random rng)
    {
        foreach (var name in Order)
        {
            var a = _p[name];
            if (!a.Enabled) continue;
            if (a.CanBeRandomlyAssigned && Roll(rng, a.RandomlyAssignedChance)) return name;
            bool meets = a.AllowedTypes.Contains(role)
                         && power > a.PowerLevelMin && power <= a.PowerLevelMax
                         && level > a.MinLevel && level <= a.MaxLevel;
            if (!meets) continue;
            var p = Math.Clamp(power, 0, 1000);
            var r = (p - a.PowerLevelScaleStart) / (a.PowerLevelScaleEnd - a.PowerLevelScaleStart);
            if (a.InverseScale) r = 1 - r;
            var chance = Math.Clamp(a.MaxChance * r, 0, 100);
            if (Roll(rng, chance)) return name;
        }
        bool isPmc = role.StartsWith("pmc", StringComparison.OrdinalIgnoreCase);
        return isPmc && Roll(rng, 33) ? "Chad" : "Normal";
    }
}
