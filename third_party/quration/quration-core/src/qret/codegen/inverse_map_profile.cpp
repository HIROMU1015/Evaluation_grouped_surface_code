/**
 * @file qret/codegen/inverse_map_profile.cpp
 * @brief Read-only instrumentation for MachineBasicBlock inverse-map usage.
 */

#include "qret/codegen/inverse_map_profile.h"

#include <algorithm>
#include <cstdlib>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "qret/codegen/machine_function.h"

namespace qret::inverse_map_profile {
namespace {
struct StageCounters {
    std::uint64_t construct_count = 0;
    std::uint64_t ensure_count = 0;
    std::uint64_t ensure_valid_count = 0;
    std::uint64_t ensure_rebuild_needed_count = 0;
    std::uint64_t lazy_rebuild_count = 0;
    std::uint64_t contain_count = 0;
    std::uint64_t contain_hit_count = 0;
    std::uint64_t contain_miss_count = 0;
    std::uint64_t insert_before_count = 0;
    std::uint64_t insert_after_count = 0;
    std::uint64_t erase_count = 0;
    std::uint64_t release_count = 0;
};

struct ProfileStats {
    std::uint64_t construct_inverse_map_count = 0;
    std::uint64_t eager_construction_count = 0;
    std::uint64_t lazy_construction_count = 0;
    std::uint64_t construct_when_valid_count = 0;
    std::uint64_t construct_after_release_count = 0;
    std::uint64_t full_rebuild_count = 0;
    std::uint64_t initial_inserted_entries = 0;
    std::uint64_t lazy_inserted_entries = 0;
    std::uint64_t constructed_entries_total = 0;
    std::uint64_t ensure_inverse_map_count = 0;
    std::uint64_t ensure_valid_count = 0;
    std::uint64_t ensure_rebuild_needed_count = 0;
    std::uint64_t lazy_rebuild_count = 0;
    std::uint64_t lazy_rebuild_after_release_count = 0;
    std::uint64_t contain_count = 0;
    std::uint64_t contain_hit_count = 0;
    std::uint64_t contain_miss_count = 0;
    std::uint64_t insert_before_count = 0;
    std::uint64_t insert_after_count = 0;
    std::uint64_t erase_count = 0;
    std::uint64_t release_count = 0;
    std::uint64_t release_valid_count = 0;
    std::uint64_t released_entries_total = 0;
    std::uint64_t final_entries_before_release_total = 0;
    std::uint64_t largest_release_block_entries = 0;
    std::uint64_t current_entries = 0;
    std::uint64_t max_live_entries = 0;
    std::uint64_t min_live_entries = std::numeric_limits<std::uint64_t>::max();
    bool observed_live_entries = false;
    bool observed_block_universe = false;
    std::uint64_t block_universe_count = 0;
    std::unordered_set<const MachineBasicBlock*> constructed_blocks;
    std::vector<std::uint64_t> construct_block_entries;
    std::vector<std::uint64_t> release_block_entries;
    std::map<std::string, StageCounters> stage_counters;
};

std::mutex Mutex;
std::optional<bool> EnabledCache;
ProfileStats Stats;
thread_local std::string CurrentStage = "unscoped";

bool ParseEnabledEnv() {
    const auto* raw = std::getenv("QRET_PROFILE_INVERSE_MAP_USAGE");
    if (raw == nullptr || std::string(raw).empty() || std::string(raw) == "0") {
        return false;
    }
    if (std::string(raw) == "1") {
        return true;
    }
    throw std::invalid_argument("QRET_PROFILE_INVERSE_MAP_USAGE must be 0 or 1");
}

std::string StageName() {
    if (CurrentStage.empty()) {
        return "unscoped";
    }
    return CurrentStage;
}

StageCounters& Stage(ProfileStats& stats) {
    return stats.stage_counters[StageName()];
}

void ObserveLiveEntries(ProfileStats& stats) {
    stats.max_live_entries = std::max(stats.max_live_entries, stats.current_entries);
    stats.min_live_entries = std::min(stats.min_live_entries, stats.current_entries);
    stats.observed_live_entries = true;
}

void AddEntries(ProfileStats& stats, std::uint64_t entries) {
    stats.current_entries += entries;
    ObserveLiveEntries(stats);
}

void RemoveEntries(ProfileStats& stats, std::uint64_t entries) {
    stats.current_entries =
            entries > stats.current_entries ? 0 : stats.current_entries - entries;
    ObserveLiveEntries(stats);
}

qret::Json StageCountersJson(const StageCounters& counters) {
    auto ret = qret::Json::object();
    ret["construct_count"] = counters.construct_count;
    ret["ensure_count"] = counters.ensure_count;
    ret["ensure_valid_count"] = counters.ensure_valid_count;
    ret["ensure_rebuild_needed_count"] = counters.ensure_rebuild_needed_count;
    ret["lazy_rebuild_count"] = counters.lazy_rebuild_count;
    ret["contain_count"] = counters.contain_count;
    ret["contain_hit_count"] = counters.contain_hit_count;
    ret["contain_miss_count"] = counters.contain_miss_count;
    ret["insert_before_count"] = counters.insert_before_count;
    ret["insert_after_count"] = counters.insert_after_count;
    ret["erase_count"] = counters.erase_count;
    ret["release_count"] = counters.release_count;
    return ret;
}
}  // namespace

bool Enabled() {
    std::lock_guard<std::mutex> lock(Mutex);
    if (!EnabledCache.has_value()) {
        EnabledCache = ParseEnabledEnv();
    }
    return *EnabledCache;
}

void ResetForTest() {
    std::lock_guard<std::mutex> lock(Mutex);
    EnabledCache.reset();
    Stats = ProfileStats();
    CurrentStage = "unscoped";
}

StageScope::StageScope(std::string stage) {
    if (!Enabled()) {
        return;
    }
    active_ = true;
    previous_ = CurrentStage;
    CurrentStage = std::move(stage);
}

StageScope::~StageScope() {
    if (active_) {
        CurrentStage = std::move(previous_);
    }
}

void RecordConstruct(
        const MachineBasicBlock& block,
        bool was_valid,
        bool was_released,
        std::size_t entries_before,
        std::size_t entries_after,
        bool from_ensure
) {
    if (!Enabled()) {
        return;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    auto& stage = Stage(Stats);
    const auto stage_name = StageName();
    ++Stats.construct_inverse_map_count;
    ++Stats.full_rebuild_count;
    ++stage.construct_count;
    Stats.constructed_blocks.insert(&block);
    if (was_valid) {
        ++Stats.construct_when_valid_count;
        RemoveEntries(Stats, static_cast<std::uint64_t>(entries_before));
    } else if (!was_released && !from_ensure) {
        Stats.initial_inserted_entries += static_cast<std::uint64_t>(entries_after);
    }
    if (stage_name == "routing_setup_construct_inverse_map") {
        ++Stats.eager_construction_count;
    }
    if (was_released) {
        ++Stats.construct_after_release_count;
    }
    Stats.constructed_entries_total += static_cast<std::uint64_t>(entries_after);
    Stats.construct_block_entries.push_back(static_cast<std::uint64_t>(entries_after));
    AddEntries(Stats, static_cast<std::uint64_t>(entries_after));
}

void RecordEnsure(const MachineBasicBlock&, bool was_valid, bool) {
    if (!Enabled()) {
        return;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    auto& stage = Stage(Stats);
    ++Stats.ensure_inverse_map_count;
    ++stage.ensure_count;
    if (was_valid) {
        ++Stats.ensure_valid_count;
        ++stage.ensure_valid_count;
    } else {
        ++Stats.ensure_rebuild_needed_count;
        ++stage.ensure_rebuild_needed_count;
    }
}

void RecordLazyRebuild(
        const MachineBasicBlock&,
        bool was_released,
        std::size_t entries_after
) {
    if (!Enabled()) {
        return;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    auto& stage = Stage(Stats);
    ++Stats.lazy_construction_count;
    Stats.lazy_inserted_entries += static_cast<std::uint64_t>(entries_after);
    ++Stats.lazy_rebuild_count;
    ++stage.lazy_rebuild_count;
    if (was_released) {
        ++Stats.lazy_rebuild_after_release_count;
    }
}

void RecordContain(const MachineBasicBlock&, bool hit, std::size_t) {
    if (!Enabled()) {
        return;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    auto& stage = Stage(Stats);
    ++Stats.contain_count;
    ++stage.contain_count;
    if (hit) {
        ++Stats.contain_hit_count;
        ++stage.contain_hit_count;
    } else {
        ++Stats.contain_miss_count;
        ++stage.contain_miss_count;
    }
}

void RecordInsertBefore(const MachineBasicBlock&, std::size_t) {
    if (!Enabled()) {
        return;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    auto& stage = Stage(Stats);
    ++Stats.insert_before_count;
    ++stage.insert_before_count;
    AddEntries(Stats, 1);
}

void RecordInsertAfter(const MachineBasicBlock&, std::size_t) {
    if (!Enabled()) {
        return;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    auto& stage = Stage(Stats);
    ++Stats.insert_after_count;
    ++stage.insert_after_count;
    AddEntries(Stats, 1);
}

void RecordErase(const MachineBasicBlock&, std::size_t) {
    if (!Enabled()) {
        return;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    auto& stage = Stage(Stats);
    ++Stats.erase_count;
    ++stage.erase_count;
    RemoveEntries(Stats, 1);
}

void RecordRelease(const MachineBasicBlock&, bool was_valid, std::size_t entries_before) {
    if (!Enabled()) {
        return;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    auto& stage = Stage(Stats);
    const auto entries = static_cast<std::uint64_t>(entries_before);
    ++Stats.release_count;
    ++stage.release_count;
    if (was_valid) {
        ++Stats.release_valid_count;
        Stats.released_entries_total += entries;
        Stats.final_entries_before_release_total += entries;
        Stats.largest_release_block_entries =
                std::max(Stats.largest_release_block_entries, entries);
        Stats.release_block_entries.push_back(entries);
        RemoveEntries(Stats, entries);
    }
}

void RecordBlockUniverse(const MachineFunction& mf) {
    if (!Enabled()) {
        return;
    }
    auto count = std::uint64_t{0};
    for ([[maybe_unused]] const auto& block : mf) {
        ++count;
    }
    std::lock_guard<std::mutex> lock(Mutex);
    Stats.observed_block_universe = true;
    Stats.block_universe_count = std::max(Stats.block_universe_count, count);
}

qret::Json SnapshotJson() {
    if (!Enabled()) {
        return qret::Json::object();
    }
    std::lock_guard<std::mutex> lock(Mutex);
    using InverseMap = std::map<
            const qret::MachineInstruction*,
            qret::MachineBasicBlock::ConstIterator>;

    auto stages = qret::Json::object();
    for (const auto& [name, counters] : Stats.stage_counters) {
        stages[name] = StageCountersJson(counters);
    }

    auto ret = qret::Json::object();
    ret["schema"] = "qret_inverse_map_usage_profile_v1";
    ret["enabled"] = true;
    ret["construct_inverse_map_count"] = Stats.construct_inverse_map_count;
    ret["eager_construction_count"] = Stats.eager_construction_count;
    ret["lazy_construction_count"] = Stats.lazy_construction_count;
    ret["construct_when_valid_count"] = Stats.construct_when_valid_count;
    ret["construct_after_release_count"] = Stats.construct_after_release_count;
    ret["full_rebuild_count"] = Stats.full_rebuild_count;
    ret["initial_inserted_entries"] = Stats.initial_inserted_entries;
    ret["lazy_inserted_entries"] = Stats.lazy_inserted_entries;
    ret["constructed_entries_total"] = Stats.constructed_entries_total;
    ret["ensure_inverse_map_count"] = Stats.ensure_inverse_map_count;
    ret["ensure_valid_count"] = Stats.ensure_valid_count;
    ret["ensure_noop_count"] = Stats.ensure_valid_count;
    ret["ensure_rebuild_needed_count"] = Stats.ensure_rebuild_needed_count;
    ret["lazy_rebuild_count"] = Stats.lazy_rebuild_count;
    ret["lazy_rebuild_after_release_count"] = Stats.lazy_rebuild_after_release_count;
    ret["contain_count"] = Stats.contain_count;
    ret["contain_hit_count"] = Stats.contain_hit_count;
    ret["contain_miss_count"] = Stats.contain_miss_count;
    ret["insert_before_count"] = Stats.insert_before_count;
    ret["insert_after_count"] = Stats.insert_after_count;
    ret["erase_count"] = Stats.erase_count;
    ret["release_count"] = Stats.release_count;
    ret["release_valid_count"] = Stats.release_valid_count;
    ret["released_entries_total"] = Stats.released_entries_total;
    ret["final_entries_before_release_total"] = Stats.final_entries_before_release_total;
    ret["largest_release_block_entries"] = Stats.largest_release_block_entries;
    ret["current_entries"] = Stats.current_entries;
    ret["max_live_entries"] = Stats.max_live_entries;
    ret["min_live_entries"] =
            Stats.observed_live_entries ? Stats.min_live_entries : std::uint64_t{0};
    ret["block_universe_count"] =
            Stats.observed_block_universe ? Stats.block_universe_count : std::uint64_t{0};
    ret["constructed_block_count"] =
            static_cast<std::uint64_t>(Stats.constructed_blocks.size());
    ret["never_constructed_block_count"] =
            Stats.observed_block_universe
            ? Stats.block_universe_count
                    - std::min(
                            Stats.block_universe_count,
                            static_cast<std::uint64_t>(Stats.constructed_blocks.size())
                    )
            : std::uint64_t{0};
    ret["construct_block_entries"] = Stats.construct_block_entries;
    ret["release_block_entries"] = Stats.release_block_entries;
    ret["stage_counters"] = stages;
    ret["map_key_size_bytes"] = sizeof(const qret::MachineInstruction*);
    ret["map_mapped_iterator_size_bytes"] =
            sizeof(qret::MachineBasicBlock::ConstIterator);
    ret["map_value_type_size_bytes"] = sizeof(typename InverseMap::value_type);
    ret["map_node_overhead_estimated_bytes"] = 3 * sizeof(void*);
    ret["map_node_bytes_estimated"] =
            sizeof(typename InverseMap::value_type) + 3 * sizeof(void*);
    ret["vector_const_iterator_size_bytes"] =
            sizeof(qret::MachineBasicBlock::ConstIterator);
    ret["stable_instruction_id_size_bytes"] = sizeof(std::uint32_t);
    ret["pointer_size_bytes"] = sizeof(void*);
    return ret;
}
}  // namespace qret::inverse_map_profile
