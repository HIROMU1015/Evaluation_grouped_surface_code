/**
 * @file qret/target/sc_ls_fixed_v0/memory_profile_stats.h
 * @brief Profiling-only estimated memory statistics for SC_LS_FIXED_V0.
 */

#ifndef QRET_TARGET_SC_LS_FIXED_V0_MEMORY_PROFILE_STATS_H
#define QRET_TARGET_SC_LS_FIXED_V0_MEMORY_PROFILE_STATS_H

#include "qret/base/json.h"
#include "qret/codegen/machine_function.h"
#include "qret/qret_export.h"

namespace qret::sc_ls_fixed_v0 {
class InstQueue;
class ScLsSimulator;

QRET_EXPORT qret::Json JsonDomMemoryStats(const qret::Json& j);
QRET_EXPORT qret::Json MachineFunctionMemoryStats(const qret::MachineFunction& mf);
QRET_EXPORT qret::Json RoutingLiveMemoryStats(
        const qret::MachineFunction& mf,
        const InstQueue* queue = nullptr,
        const ScLsSimulator* simulator = nullptr
);
}  // namespace qret::sc_ls_fixed_v0

#endif  // QRET_TARGET_SC_LS_FIXED_V0_MEMORY_PROFILE_STATS_H
