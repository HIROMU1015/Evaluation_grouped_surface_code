/**
 * @file qret/target/sc_ls_fixed_v0/magic_path_storage.h
 * @brief Storage policy for LATTICE_SURGERY_MAGIC paths.
 */

#ifndef QRET_TARGET_SC_LS_FIXED_V0_MAGIC_PATH_STORAGE_H
#define QRET_TARGET_SC_LS_FIXED_V0_MAGIC_PATH_STORAGE_H

#include <cstdint>
#include <list>
#include <memory>

#include "qret/base/json.h"
#include "qret/qret_export.h"
#include "qret/target/sc_ls_fixed_v0/topology.h"

namespace qret::sc_ls_fixed_v0 {

enum class MagicPathStorageMode : std::uint8_t {
    LegacyList,
    Interned,
};

using MagicPathList = std::list<Coord3D>;
using MagicPathHandle = std::shared_ptr<const MagicPathList>;

struct MagicPathStorage {
    MagicPathList list;
    MagicPathHandle handle;
};

QRET_EXPORT MagicPathStorageMode ParseMagicPathStorageMode();
QRET_EXPORT const char* ToString(MagicPathStorageMode mode);
QRET_EXPORT MagicPathStorage MakeMagicPathStorage(const MagicPathList& path);
QRET_EXPORT MagicPathStorage MakeMagicPathStorage(MagicPathList&& path);
QRET_EXPORT void SetMagicPathStorage(MagicPathStorage& storage, const MagicPathList& path);
QRET_EXPORT void SetMagicPathStorage(MagicPathStorage& storage, MagicPathList&& path);
QRET_EXPORT const MagicPathList& MagicPathStorageList(const MagicPathStorage& storage);
QRET_EXPORT bool MagicPathStorageUsesHandle(const MagicPathStorage& storage);
QRET_EXPORT const void* MagicPathStorageIdentity(const MagicPathStorage& storage);
QRET_EXPORT MagicPathHandle MagicPathStorageHandleForTest(const MagicPathStorage& storage);

class QRET_EXPORT MagicPathInterner {
public:
    explicit MagicPathInterner(bool force_hash_collision_for_test = false);
    MagicPathInterner(const MagicPathInterner&) = delete;
    MagicPathInterner& operator=(const MagicPathInterner&) = delete;
    MagicPathInterner(MagicPathInterner&&) = delete;
    MagicPathInterner& operator=(MagicPathInterner&&) = delete;
    ~MagicPathInterner();

    [[nodiscard]] MagicPathHandle Intern(const MagicPathList& path);
    [[nodiscard]] MagicPathHandle Intern(MagicPathList&& path);
    [[nodiscard]] qret::Json Stats() const;

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

class QRET_EXPORT MagicPathInterningScope {
public:
    explicit MagicPathInterningScope(MagicPathInterner& interner);
    MagicPathInterningScope(const MagicPathInterningScope&) = delete;
    MagicPathInterningScope& operator=(const MagicPathInterningScope&) = delete;
    MagicPathInterningScope(MagicPathInterningScope&&) = delete;
    MagicPathInterningScope& operator=(MagicPathInterningScope&&) = delete;
    ~MagicPathInterningScope();

private:
    MagicPathInterner* interner_;
    MagicPathInterner* previous_;
};

QRET_EXPORT qret::Json CurrentMagicPathInternerStats();
QRET_EXPORT qret::Json LastMagicPathInternerStats();

}  // namespace qret::sc_ls_fixed_v0

#endif  // QRET_TARGET_SC_LS_FIXED_V0_MAGIC_PATH_STORAGE_H
