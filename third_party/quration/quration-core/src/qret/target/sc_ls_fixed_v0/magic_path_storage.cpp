/**
 * @file qret/target/sc_ls_fixed_v0/magic_path_storage.cpp
 * @brief Storage policy for LATTICE_SURGERY_MAGIC paths.
 */

#include "qret/target/sc_ls_fixed_v0/magic_path_storage.h"

#include <fmt/format.h>

#include <algorithm>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace qret::sc_ls_fixed_v0 {
namespace {
thread_local MagicPathInterner* current_interner = nullptr;  // NOLINT
thread_local qret::Json last_interner_stats = qret::Json::object();  // NOLINT

std::uint64_t MixHash(std::uint64_t hash, std::uint64_t value) {
    hash ^= value;
    hash *= 1099511628211ULL;
    return hash;
}

std::uint64_t SignedBits(std::int32_t value) {
    return static_cast<std::uint64_t>(static_cast<std::uint32_t>(value));
}

std::uint64_t HashPath(const MagicPathList& path) {
    auto hash = std::uint64_t{1469598103934665603ULL};
    hash = MixHash(hash, static_cast<std::uint64_t>(path.size()));
    for (const auto& coord : path) {
        hash = MixHash(hash, SignedBits(coord.x));
        hash = MixHash(hash, SignedBits(coord.y));
        hash = MixHash(hash, SignedBits(coord.z));
    }
    return hash;
}

bool EqualPath(const MagicPathList& lhs, const MagicPathList& rhs) {
    return lhs.size() == rhs.size()
            && std::equal(lhs.begin(), lhs.end(), rhs.begin(), rhs.end());
}

double Percent(std::uint64_t part, std::uint64_t total) {
    return total == 0 ? 0.0 : 100.0 * static_cast<double>(part) / static_cast<double>(total);
}

std::uint64_t ListNodeBytes() {
    return static_cast<std::uint64_t>(sizeof(Coord3D) + 2 * sizeof(void*));
}

}  // namespace

class MagicPathInterner::Impl {
public:
    explicit Impl(bool force_hash_collision)
        : force_hash_collision_(force_hash_collision) {}

    MagicPathHandle Intern(const MagicPathList& path) {
        ++assignment_count_;
        const auto hash = force_hash_collision_ ? std::uint64_t{0} : HashPath(path);
        auto& bucket = buckets_[hash];
        for (const auto& handle : bucket) {
            ++key_compare_count_;
            if (EqualPath(path, *handle)) {
                ++hit_count_;
                return handle;
            }
        }
        if (!bucket.empty()) {
            ++hash_collision_distinct_key_count_;
        }
        ++miss_count_;
        unique_coordinate_count_ += static_cast<std::uint64_t>(path.size());
        auto handle = std::make_shared<MagicPathList>(path);
        bucket.push_back(handle);
        max_hash_bucket_size_ =
                std::max(max_hash_bucket_size_, static_cast<std::uint64_t>(bucket.size()));
        return handle;
    }

    MagicPathHandle Intern(MagicPathList&& path) {
        ++assignment_count_;
        const auto hash = force_hash_collision_ ? std::uint64_t{0} : HashPath(path);
        auto& bucket = buckets_[hash];
        for (const auto& handle : bucket) {
            ++key_compare_count_;
            if (EqualPath(path, *handle)) {
                ++hit_count_;
                return handle;
            }
        }
        if (!bucket.empty()) {
            ++hash_collision_distinct_key_count_;
        }
        ++miss_count_;
        unique_coordinate_count_ += static_cast<std::uint64_t>(path.size());
        auto handle = std::make_shared<MagicPathList>(std::move(path));
        bucket.push_back(handle);
        max_hash_bucket_size_ =
                std::max(max_hash_bucket_size_, static_cast<std::uint64_t>(bucket.size()));
        return handle;
    }

    [[nodiscard]] qret::Json Stats() const {
        auto unique_paths = std::uint64_t{0};
        for (const auto& [_, bucket] : buckets_) {
            unique_paths += static_cast<std::uint64_t>(bucket.size());
        }
        auto ret = qret::Json::object();
        ret["magic_path_storage_mode"] = ToString(ParseMagicPathStorageMode());
        ret["magic_path_assignment_count"] = assignment_count_;
        ret["magic_path_unique_interned_path_count"] = unique_paths;
        ret["magic_path_intern_hit_count"] = hit_count_;
        ret["magic_path_intern_miss_count"] = miss_count_;
        ret["magic_path_intern_hit_rate_percent"] = Percent(hit_count_, assignment_count_);
        ret["magic_path_unique_coordinate_count"] = unique_coordinate_count_;
        ret["magic_path_unique_payload_bytes_estimated"] =
                unique_coordinate_count_ * static_cast<std::uint64_t>(sizeof(Coord3D));
        ret["magic_path_unique_list_node_bytes_estimated"] =
                unique_coordinate_count_ * ListNodeBytes();
        ret["magic_path_unique_list_object_bytes_estimated"] =
                unique_paths * static_cast<std::uint64_t>(sizeof(MagicPathList));
        ret["magic_path_per_instruction_handle_bytes"] = sizeof(MagicPathHandle);
        ret["magic_path_handle_total_bytes_estimated"] =
                assignment_count_ * static_cast<std::uint64_t>(sizeof(MagicPathHandle));
        ret["magic_path_interner_hash_bucket_count"] = buckets_.size();
        ret["magic_path_interner_hash_max_bucket_size"] = max_hash_bucket_size_;
        ret["magic_path_interner_hash_key_compare_count"] = key_compare_count_;
        ret["magic_path_interner_hash_collision_distinct_key_count"] =
                hash_collision_distinct_key_count_;
        ret["magic_path_interner_hash_collision_fallback_used"] =
                hash_collision_distinct_key_count_ > 0;
        ret["magic_path_interner_hash_table_estimated_bytes"] =
                buckets_.size() * static_cast<std::uint64_t>(sizeof(void*) + sizeof(std::uint64_t))
                + unique_paths * static_cast<std::uint64_t>(sizeof(MagicPathHandle) + sizeof(void*));
        ret["magic_path_interner_temporary_peak_bytes_estimated"] =
                ret["magic_path_interner_hash_table_estimated_bytes"];
        return ret;
    }

private:
    bool force_hash_collision_ = false;
    std::unordered_map<std::uint64_t, std::vector<MagicPathHandle>> buckets_;
    std::uint64_t assignment_count_ = 0;
    std::uint64_t hit_count_ = 0;
    std::uint64_t miss_count_ = 0;
    std::uint64_t unique_coordinate_count_ = 0;
    std::uint64_t max_hash_bucket_size_ = 0;
    std::uint64_t key_compare_count_ = 0;
    std::uint64_t hash_collision_distinct_key_count_ = 0;
};

MagicPathStorageMode ParseMagicPathStorageMode() {
    const auto* raw = std::getenv("QRET_MAGIC_PATH_STORAGE");
    if (raw == nullptr || std::string(raw).empty() || std::string(raw) == "interned") {
        return MagicPathStorageMode::Interned;
    }
    const auto value = std::string(raw);
    if (value == "legacy" || value == "legacy_list") {
        return MagicPathStorageMode::LegacyList;
    }
    throw std::invalid_argument("QRET_MAGIC_PATH_STORAGE must be legacy_list or interned");
}

const char* ToString(MagicPathStorageMode mode) {
    switch (mode) {
        case MagicPathStorageMode::LegacyList:
            return "legacy_list";
        case MagicPathStorageMode::Interned:
            return "interned";
        default:
            break;
    }
    throw std::runtime_error("unknown MagicPathStorageMode");
}

MagicPathStorage MakeMagicPathStorage(const MagicPathList& path) {
    auto storage = MagicPathStorage{};
    SetMagicPathStorage(storage, path);
    return storage;
}

MagicPathStorage MakeMagicPathStorage(MagicPathList&& path) {
    auto storage = MagicPathStorage{};
    SetMagicPathStorage(storage, std::move(path));
    return storage;
}

void SetMagicPathStorage(MagicPathStorage& storage, const MagicPathList& path) {
    if (ParseMagicPathStorageMode() == MagicPathStorageMode::LegacyList
        || current_interner == nullptr) {
        storage.handle.reset();
        storage.list = path;
        return;
    }
    storage.handle = current_interner->Intern(path);
    storage.list.clear();
}

void SetMagicPathStorage(MagicPathStorage& storage, MagicPathList&& path) {
    if (ParseMagicPathStorageMode() == MagicPathStorageMode::LegacyList
        || current_interner == nullptr) {
        storage.handle.reset();
        storage.list = std::move(path);
        return;
    }
    storage.handle = current_interner->Intern(std::move(path));
    storage.list.clear();
}

const MagicPathList& MagicPathStorageList(const MagicPathStorage& storage) {
    return storage.handle == nullptr ? storage.list : *storage.handle;
}

bool MagicPathStorageUsesHandle(const MagicPathStorage& storage) {
    return storage.handle != nullptr;
}

const void* MagicPathStorageIdentity(const MagicPathStorage& storage) {
    return storage.handle == nullptr ? static_cast<const void*>(&storage.list)
                                     : static_cast<const void*>(storage.handle.get());
}

MagicPathHandle MagicPathStorageHandleForTest(const MagicPathStorage& storage) {
    return storage.handle;
}

MagicPathInterner::MagicPathInterner(bool force_hash_collision_for_test)
    : impl_(std::make_unique<Impl>(force_hash_collision_for_test)) {}

MagicPathInterner::~MagicPathInterner() = default;

MagicPathHandle MagicPathInterner::Intern(const MagicPathList& path) {
    return impl_->Intern(path);
}

MagicPathHandle MagicPathInterner::Intern(MagicPathList&& path) {
    return impl_->Intern(std::move(path));
}

qret::Json MagicPathInterner::Stats() const {
    return impl_->Stats();
}

MagicPathInterningScope::MagicPathInterningScope(MagicPathInterner& interner)
    : interner_(&interner)
    , previous_(current_interner) {
    current_interner = &interner;
}

MagicPathInterningScope::~MagicPathInterningScope() {
    last_interner_stats = interner_->Stats();
    current_interner = previous_;
}

qret::Json CurrentMagicPathInternerStats() {
    return current_interner == nullptr ? qret::Json::object() : current_interner->Stats();
}

qret::Json LastMagicPathInternerStats() {
    return last_interner_stats;
}
}  // namespace qret::sc_ls_fixed_v0
