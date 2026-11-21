# FullBodyArmor

Modular full-body armor and three tiers of powered exoskeletons for **SPT 4.0.x** (EFT 0.16.9). Fika compatible.

## Features

### FBA modular full-body armor
- A carrier based on the FORT Redut-T5 with **no built-in protection**. Every zone takes a removable plate or panel: torso, sides, neck, shoulders, groin, thighs, calves and forearms.
- 20 removable Aramid pieces, each in **class 5 or class 6**. Limb pieces are as durable as torso pieces.
- **Armored GigaChads.** A configurable share of GigaChad PMCs (20% by default) spawn in a full class 5 or full class 6 set. They also get Tagilla-level skills, the "ZABEY" welding mask (a lootable copy), a unique weapon build and spare magazines. They fight like a boss, and killing one is the only way to get the set: the carrier and pieces can't be sold on the flea market and aren't sold by traders.

### EXO exoskeletons (sold by Ragman)
| Tier | Item | Ragman LL | Built-in protection |
|---|---|---|---|
| 1 | EXO-1 construction exoskeleton | 2 | class 3 soft front/back |
| 2 | EXO-2 military exoskeleton | 3 | class 3 soft front/back |
| 3 | EXO-3 assault exoskeleton | 4 | titanium plates: class 4 torso, class 3 sides/neck/shoulders/forearms/groin/thighs/calves (titanium repairs poorly) |

| Bonus (per tier 1 / 2 / 3) | |
|---|---|
| Sprint speed | ×1.15 / ×1.20 / ×1.25 |
| Sprint and arm stamina drain | ×0.75 / ×0.65 / ×0.55 |
| Weight limits | +15 / +25 / +35 kg |
| Jump height | ×1.25 / ×1.35 / ×1.45 |
| Melee damage | ×2.0 / ×2.5 / ×3.0 |
| Fall damage cushion | 0.5 / 1.0 / 1.5 m |
| Vaulting while overweight | ×1.15 / ×1.20 / ×1.25 |
| Recoil | — / ×0.95 / ×0.90 |

The price for these bonuses: an exoskeleton **can't be worn with any armored gear**, including armored helmets, masks, glasses and ballistic rigs. Regular clothing and gear still work.

### Localization
All item texts are in `server/locales.json` for all 17 SPT languages. A missing key falls back to English.

## Requirements
- SPT 4.0.x
- [SAIN](https://forge.sp-tarkov.com/) 4.x (required; the client plugin also fixes SAIN 4.4.2 personality assignment for PMCs)
- Fika (optional)

## Installation
Extract the release archive into your SPT folder:
```
SPT/user/mods/FullBodyArmor/            server mod (DLL, locales.json, config.json, bundles)
BepInEx/plugins/FullBodyArmorClient/    client plugin
```
For Fika headless, also copy the client plugin into the headless client's `BepInEx/plugins`.

## Configuration (`SPT/user/mods/FullBodyArmor/config.json`)
| Key | Default | Meaning |
|---|---|---|
| `GigaChadArmorEnabled` | `true` | Armored GigaChads on/off |
| `ArmoredGigaChadShare` | `0.2` | Share of GigaChad PMCs that get the armor |
| `Class6Share` | `0.5` | Share of armored ones that get class 6 (the rest get class 5) |
| `SainPluginDir` | `../BepInEx/plugins/SAIN` | Where the server reads SAIN presets from |
| `TestScavsWearCarrier` | `false` | Debug: every Scav wears the carrier |

## Building from source
Requires the .NET 9 SDK and an SPT install (the projects reference its DLLs).
```
dotnet build server -c Release -p:SptDir=C:\SPT
dotnet build client -c Release -p:SptDir=C:\SPT
```
`SptDir` defaults to `C:\SPT`.

## Repository layout
| Path | Contents |
|---|---|
| `server/` | Server mod (C#, net9.0): items, armor kits, GigaChad bot post-processing, exoskeleton items, localization |
| `server/config/` | Default `config.json`, `bundles.json`, weapon builds, magazine sanitize table |
| `client/` | BepInEx plugin (C#, netstandard2.1): exoskeleton mechanics, SAIN fixes |
| `tools/` | Asset pipeline scripts: Blender export and checks, Unity bundle build, bundle patching |
| `tools/exo_model/` | Blender scripts that build the exoskeleton models procedurally |

Obfuscated game members are resolved at runtime by signature (`client/ExoResolve.cs`), not by their obfuscated names. None of this mod's code is obfuscated.

## License
See [LICENSE](LICENSE).
