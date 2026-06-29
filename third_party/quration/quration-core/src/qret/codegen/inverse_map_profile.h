/**
 * @file qret/codegen/inverse_map_profile.h
 * @brief Read-only instrumentation for MachineBasicBlock inverse-map usage.
 */

#ifndef QRET_CODEGEN_INVERSE_MAP_PROFILE_H
#define QRET_CODEGEN_INVERSE_MAP_PROFILE_H

#include <cstddef>
#include <cstdint>
#include <string>

#include "qret/base/json.h"
#include "qret/qret_export.h"

namespace qret {
class MachineBasicBlock;
class MachineFunction;

namespace inverse_map_profile {
QRET_EXPORT bool Enabled();
QRET_EXPORT void ResetForTest();

class QRET_EXPORT StageScope {
public:
    explicit StageScope(std::string stage);
    StageScope(const StageScope&) = delete;
    StageScope& operator=(const StageScope&) = delete;
    ~StageScope();

private:
    bool active_ = false;
    std::string previous_;
};

QRET_EXPORT void RecordConstruct(
        const MachineBasicBlock& block,
        bool was_valid,
        bool was_released,
        std::size_t entries_before,
        std::size_t entries_after,
        bool from_ensure
);
QRET_EXPORT void RecordEnsure(
        const MachineBasicBlock& block,
        bool was_valid,
        bool was_released
);
QRET_EXPORT void RecordLazyRebuild(
        const MachineBasicBlock& block,
        bool was_released,
        std::size_t entries_after
);
QRET_EXPORT void RecordContain(
        const MachineBasicBlock& block,
        bool hit,
        std::size_t entries_after
);
QRET_EXPORT void RecordInsertBefore(const MachineBasicBlock& block, std::size_t entries_after);
QRET_EXPORT void RecordInsertAfter(const MachineBasicBlock& block, std::size_t entries_after);
QRET_EXPORT void RecordErase(const MachineBasicBlock& block, std::size_t entries_after);
QRET_EXPORT void RecordRelease(
        const MachineBasicBlock& block,
        bool was_valid,
        std::size_t entries_before
);
QRET_EXPORT void RecordBlockUniverse(const MachineFunction& mf);
QRET_EXPORT qret::Json SnapshotJson();
}  // namespace inverse_map_profile
}  // namespace qret

#endif  // QRET_CODEGEN_INVERSE_MAP_PROFILE_H
