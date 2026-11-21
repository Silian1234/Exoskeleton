// FBA items are obtainable ONLY from armored GigaChad PMCs (and the BlueheadsAIOTrader debug trader, which lists the whole DB).
// No traders/crafts/barters/quests add them by themselves; here they are excluded from every random-item generator.
// ItemConfig.Blacklist is NOT used on purpose: it marks items as invalid (profile cleanup, AIO trader would drop them).
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using SPTarkov.DI.Annotations;
using SPTarkov.Server.Core.DI;
using SPTarkov.Server.Core.Models.Common;
using SPTarkov.Server.Core.Models.Spt.Config;
using SPTarkov.Server.Core.Models.Utils;
using System.Threading;
using SPTarkov.Common.Models.Logging;
using SPTarkov.Server.Core.Models.Spt.Tables;

namespace FullBodyArmor;

[Injectable(InjectionType.Singleton, OnLoadOrder.Preload + 3)]
public class FbaExclusivity(ISptLogger<FbaExclusivity> logger, ItemConfig itemConfig, AirdropConfig airdropConfig,
    ScavCaseConfig scavCaseConfig, TraderConfig traderConfig, PmcConfig pmcConfig, QuestConfig questConfig,
    HideoutConfig hideoutConfig, RagfairConfig ragfairConfig) : IOnLoad
{
    public Task OnLoadAsync(CancellationToken cancellationToken)
    {
        var ids = FullBodyArmorLoader.RegisteredIds.ToList();
        if (ids.Count == 0) return Task.CompletedTask;
        int lists = 0;
        void Add(ICollection<MongoId> c)
        {
            if (c == null) return;
            foreach (var id in ids) if (!c.Contains(id)) c.Add(id);
            lists++;
        }

        var item = itemConfig;
        Add(item.RewardItemBlacklist);                       // quest/coop/airdrop rewards that honour it

        foreach (var loot in airdropConfig.Loot.Values) Add(loot.ItemBlacklist);
        Add(scavCaseConfig.RewardItemBlacklist);
        Add(traderConfig.Fence?.Blacklist);
        Add(pmcConfig.GlobalLootBlacklist);   // random loot in PMC backpacks/pockets
        foreach (var rq in questConfig.RepeatableQuests ?? new()) Add(rq.RewardBlacklist);
        Add(hideoutConfig.CultistCircle?.RewardItemBlacklist);
        Add(ragfairConfig.Dynamic?.Blacklist?.Custom);

        logger.Info($"[FullBodyArmor] exclusivity: {ids.Count} items blacklisted in {lists} generator lists");
        return Task.CompletedTask;
    }
}
