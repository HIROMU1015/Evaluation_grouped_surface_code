/**
 * @file qret/target/sc_ls_fixed_v0/magic_path_profile.h
 * @brief Opt-in profiling for LATTICE_SURGERY_MAGIC path storage.
 */

#ifndef QRET_TARGET_SC_LS_FIXED_V0_MAGIC_PATH_PROFILE_H
#define QRET_TARGET_SC_LS_FIXED_V0_MAGIC_PATH_PROFILE_H

#include <list>
#include <string_view>
#include <vector>

#include "qret/base/json.h"
#include "qret/codegen/machine_function.h"
#include "qret/qret_export.h"
#include "qret/target/sc_ls_fixed_v0/topology.h"

namespace qret::sc_ls_fixed_v0 {

QRET_EXPORT bool MagicPathProfilingEnabled();
QRET_EXPORT qret::Json MagicPathProfileForPathsForTest(
        const std::vector<std::list<Coord3D>>& paths,
        bool force_hash_collision = false
);
QRET_EXPORT qret::Json LatticeSurgeryMagicPathMemoryProfile(const qret::MachineFunction& mf);
QRET_EXPORT void MaybeWriteLatticeSurgeryMagicPathProfile(
        const qret::MachineFunction& mf,
        std::string_view stage
);
QRET_EXPORT std::size_t MagicPathSegmentCountForTest(const std::list<Coord3D>& path);

}  // namespace qret::sc_ls_fixed_v0

#endif  // QRET_TARGET_SC_LS_FIXED_V0_MAGIC_PATH_PROFILE_H
