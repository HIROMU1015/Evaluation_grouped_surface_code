/**
 * @file qret/target/sc_ls_fixed_v0/magic_path_profile.cpp
 * @brief Opt-in profiling for LATTICE_SURGERY_MAGIC path storage.
 */

#include "qret/target/sc_ls_fixed_v0/magic_path_profile.h"

#include <fmt/format.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>

#include "qret/base/rss_profile.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
#include "qret/target/sc_ls_fixed_v0/pauli.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
using PathVector = std::vector<Coord3D>;

constexpr auto TOP_K = std::size_t{10};

std::uint64_t AlignUp(std::uint64_t value, std::uint64_t alignment) {
    if (alignment == 0) {
        return value;
    }
    const auto remainder = value % alignment;
    return remainder == 0 ? value : value + alignment - remainder;
}

template <typename T>
std::uint64_t ListNodeBytesUnaligned() {
    return static_cast<std::uint64_t>(sizeof(T) + 2 * sizeof(void*));
}

template <typename T>
std::uint64_t ListNodeBytesAligned() {
    return AlignUp(ListNodeBytesUnaligned<T>(), alignof(std::max_align_t));
}

std::uint64_t SaturatingSub(std::uint64_t lhs, std::uint64_t rhs) {
    return lhs > rhs ? lhs - rhs : 0;
}

double Percent(std::uint64_t part, std::uint64_t total) {
    return total == 0 ? 0.0 : 100.0 * static_cast<double>(part) / static_cast<double>(total);
}

std::uint64_t NextPowerOfTwo(std::uint64_t value) {
    if (value <= 1) {
        return value;
    }
    auto ret = std::uint64_t{1};
    while (ret < value) {
        ret <<= 1;
    }
    return ret;
}

qret::Json CoordJson(const Coord3D& coord) {
    return qret::Json::array({coord.x, coord.y, coord.z});
}

qret::Json CoordJsonOrNull(const PathVector& path, bool first) {
    if (path.empty()) {
        return nullptr;
    }
    return CoordJson(first ? path.front() : path.back());
}

PathVector ToVector(const std::list<Coord3D>& path) {
    return PathVector(path.begin(), path.end());
}

bool LexicographicLess(const PathVector& lhs, const PathVector& rhs) {
    return std::lexicographical_compare(lhs.begin(), lhs.end(), rhs.begin(), rhs.end());
}

PathVector ReverseCanonical(PathVector path) {
    auto reversed = path;
    std::reverse(reversed.begin(), reversed.end());
    return LexicographicLess(reversed, path) ? std::move(reversed) : std::move(path);
}

PathVector RelativeShape(const PathVector& path) {
    if (path.empty()) {
        return {};
    }
    const auto origin = path.front();
    auto shape = PathVector();
    shape.reserve(path.size());
    for (const auto& coord : path) {
        shape.push_back(Coord3D{coord.x - origin.x, coord.y - origin.y, coord.z - origin.z});
    }
    return shape;
}

PathVector Prefix(const PathVector& path, std::size_t length) {
    return PathVector(path.begin(), path.begin() + static_cast<std::ptrdiff_t>(length));
}

PathVector Suffix(const PathVector& path, std::size_t length) {
    return PathVector(path.end() - static_cast<std::ptrdiff_t>(length), path.end());
}

std::uint64_t MixHash(std::uint64_t hash, std::uint64_t value) {
    hash ^= value;
    hash *= 1099511628211ULL;
    return hash;
}

std::uint64_t SignedBits(std::int32_t value) {
    return static_cast<std::uint64_t>(static_cast<std::uint32_t>(value));
}

std::uint64_t HashPath(const PathVector& path) {
    auto hash = std::uint64_t{1469598103934665603ULL};
    hash = MixHash(hash, static_cast<std::uint64_t>(path.size()));
    for (const auto& coord : path) {
        hash = MixHash(hash, SignedBits(coord.x));
        hash = MixHash(hash, SignedBits(coord.y));
        hash = MixHash(hash, SignedBits(coord.z));
    }
    return hash;
}

struct FrequencyEntry {
    PathVector key;
    std::uint64_t count = 0;
};

class FrequencyCounter {
public:
    explicit FrequencyCounter(bool force_hash_collision = false)
        : force_hash_collision_{force_hash_collision} {}

    void Add(PathVector key) {
        ++total_count_;
        total_coordinate_count_ += static_cast<std::uint64_t>(key.size());
        const auto hash = force_hash_collision_ ? std::uint64_t{0} : HashPath(key);
        auto& bucket = buckets_[hash];
        for (auto& entry : bucket) {
            ++key_compare_count_;
            if (entry.key == key) {
                ++entry.count;
                return;
            }
        }
        if (!bucket.empty()) {
            ++hash_collision_distinct_key_count_;
        }
        unique_coordinate_count_ += static_cast<std::uint64_t>(key.size());
        ++unique_count_;
        bucket.push_back(FrequencyEntry{std::move(key), 1});
        max_hash_bucket_size_ = std::max(
                max_hash_bucket_size_,
                static_cast<std::uint64_t>(bucket.size())
        );
    }

    [[nodiscard]] std::uint64_t TotalCount() const {
        return total_count_;
    }
    [[nodiscard]] std::uint64_t UniqueCount() const {
        return unique_count_;
    }
    [[nodiscard]] std::uint64_t DuplicateCount() const {
        return SaturatingSub(total_count_, unique_count_);
    }
    [[nodiscard]] std::uint64_t UniqueCoordinateCount() const {
        return unique_coordinate_count_;
    }
    [[nodiscard]] std::uint64_t TotalCoordinateCount() const {
        return total_coordinate_count_;
    }
    [[nodiscard]] std::uint64_t SharedPathCount() const {
        auto count = std::uint64_t{0};
        for (const auto& [_, bucket] : buckets_) {
            for (const auto& entry : bucket) {
                if (entry.count > 1) {
                    count += entry.count;
                }
            }
        }
        return count;
    }
    [[nodiscard]] std::uint64_t SharedKeyCount() const {
        auto count = std::uint64_t{0};
        for (const auto& [_, bucket] : buckets_) {
            for (const auto& entry : bucket) {
                if (entry.count > 1) {
                    ++count;
                }
            }
        }
        return count;
    }
    [[nodiscard]] std::uint64_t MostFrequentCount() const {
        auto best = std::uint64_t{0};
        for (const auto& [_, bucket] : buckets_) {
            for (const auto& entry : bucket) {
                best = std::max(best, entry.count);
            }
        }
        return best;
    }

    [[nodiscard]] qret::Json SummaryJson() const {
        auto ret = qret::Json::object();
        ret["total_count"] = total_count_;
        ret["unique_count"] = unique_count_;
        ret["duplicate_count"] = DuplicateCount();
        ret["duplicate_percent"] = Percent(DuplicateCount(), total_count_);
        ret["shared_path_count"] = SharedPathCount();
        ret["shared_key_count"] = SharedKeyCount();
        ret["most_frequent_count"] = MostFrequentCount();
        ret["unique_coordinate_count"] = unique_coordinate_count_;
        ret["total_coordinate_count"] = total_coordinate_count_;
        ret["hash_bucket_count"] = buckets_.size();
        ret["hash_max_bucket_size"] = max_hash_bucket_size_;
        ret["hash_key_compare_count"] = key_compare_count_;
        ret["hash_collision_distinct_key_count"] = hash_collision_distinct_key_count_;
        ret["hash_collision_fallback_used"] = hash_collision_distinct_key_count_ > 0;
        ret["top_frequencies"] = TopJson();
        return ret;
    }

private:
    [[nodiscard]] qret::Json TopJson() const {
        auto rows = std::vector<const FrequencyEntry*>();
        for (const auto& [_, bucket] : buckets_) {
            for (const auto& entry : bucket) {
                rows.push_back(&entry);
            }
        }
        std::sort(rows.begin(), rows.end(), [](const auto* lhs, const auto* rhs) {
            if (lhs->count != rhs->count) {
                return lhs->count > rhs->count;
            }
            return lhs->key.size() < rhs->key.size();
        });
        auto ret = qret::Json::array();
        const auto limit = std::min(TOP_K, rows.size());
        for (auto i = std::size_t{0}; i < limit; ++i) {
            const auto& entry = *rows[i];
            auto item = qret::Json::object();
            item["frequency"] = entry.count;
            item["length"] = entry.key.size();
            item["first"] = CoordJsonOrNull(entry.key, true);
            item["last"] = CoordJsonOrNull(entry.key, false);
            item["hash"] = HashPath(entry.key);
            ret.emplace_back(std::move(item));
        }
        return ret;
    }

    bool force_hash_collision_ = false;
    std::unordered_map<std::uint64_t, std::vector<FrequencyEntry>> buckets_;
    std::uint64_t total_count_ = 0;
    std::uint64_t total_coordinate_count_ = 0;
    std::uint64_t unique_count_ = 0;
    std::uint64_t unique_coordinate_count_ = 0;
    std::uint64_t max_hash_bucket_size_ = 0;
    std::uint64_t key_compare_count_ = 0;
    std::uint64_t hash_collision_distinct_key_count_ = 0;
};

std::size_t SegmentCount(const PathVector& path) {
    if (path.size() < 2) {
        return 0;
    }
    auto segments = std::size_t{0};
    auto prev_delta = Coord3D{};
    auto has_prev_delta = false;
    for (auto i = std::size_t{1}; i < path.size(); ++i) {
        const auto delta = Coord3D{
                path[i].x - path[i - 1].x,
                path[i].y - path[i - 1].y,
                path[i].z - path[i - 1].z,
        };
        if (!has_prev_delta || delta != prev_delta) {
            ++segments;
            prev_delta = delta;
            has_prev_delta = true;
        }
    }
    return segments;
}

double Median(const std::vector<std::uint64_t>& sorted) {
    if (sorted.empty()) {
        return 0.0;
    }
    const auto n = sorted.size();
    if (n % 2 == 1) {
        return static_cast<double>(sorted[n / 2]);
    }
    return (static_cast<double>(sorted[n / 2 - 1]) + static_cast<double>(sorted[n / 2])) / 2.0;
}

std::uint64_t PercentileNearest(const std::vector<std::uint64_t>& sorted, double percentile) {
    if (sorted.empty()) {
        return 0;
    }
    const auto rank = static_cast<std::size_t>(
            std::ceil(percentile * static_cast<double>(sorted.size()))
    );
    const auto index = std::min(sorted.size() - 1, rank == 0 ? std::size_t{0} : rank - 1);
    return sorted[index];
}

qret::Json LengthBucketsJson(const std::map<std::string, std::uint64_t>& buckets) {
    auto ret = qret::Json::object();
    for (const auto& [name, count] : buckets) {
        ret[name] = count;
    }
    return ret;
}

std::string LengthBucket(std::uint64_t length) {
    if (length == 0) {
        return "empty";
    }
    if (length <= 4) {
        return fmt::format("length_{}", length);
    }
    if (length <= 8) {
        return "length_5_8";
    }
    if (length <= 16) {
        return "length_9_16";
    }
    if (length <= 32) {
        return "length_17_32";
    }
    if (length <= 64) {
        return "length_33_64";
    }
    return "length_65_plus";
}

struct AxisStats {
    bool seen = false;
    std::int32_t min = 0;
    std::int32_t max = 0;
    std::unordered_set<std::int32_t> unique;

    void Add(std::int32_t value) {
        if (!seen) {
            min = value;
            max = value;
            seen = true;
        } else {
            min = std::min(min, value);
            max = std::max(max, value);
        }
        unique.insert(value);
    }

    [[nodiscard]] qret::Json Json() const {
        auto ret = qret::Json::object();
        ret["min"] = seen ? qret::Json(min) : qret::Json(nullptr);
        ret["max"] = seen ? qret::Json(max) : qret::Json(nullptr);
        ret["unique_count"] = unique.size();
        ret["has_negative"] = seen && min < 0;
        ret["fits_int8"] = seen && min >= std::numeric_limits<std::int8_t>::min()
                && max <= std::numeric_limits<std::int8_t>::max();
        ret["fits_int16"] = seen && min >= std::numeric_limits<std::int16_t>::min()
                && max <= std::numeric_limits<std::int16_t>::max();
        ret["fits_int32"] = seen;
        return ret;
    }
};

class PathProfileAccumulator {
public:
    explicit PathProfileAccumulator(bool force_hash_collision = false)
        : exact_{force_hash_collision}
        , reverse_{force_hash_collision}
        , shape_{force_hash_collision} {
        for (const auto name : {
                     "empty",
                     "length_1",
                     "length_2",
                     "length_3",
                     "length_4",
                     "length_5_8",
                     "length_9_16",
                     "length_17_32",
                     "length_33_64",
                     "length_65_plus",
             }) {
            length_buckets_[name] = 0;
        }
    }

    void AddPath(const std::list<Coord3D>& path_list) {
        const auto path = ToVector(path_list);
        const auto length = static_cast<std::uint64_t>(path.size());
        ++path_count_;
        total_coordinate_count_ += length;
        length_values_.push_back(length);
        ++length_buckets_[LengthBucket(length)];

        exact_.Add(path);
        reverse_.Add(ReverseCanonical(path));
        shape_.Add(RelativeShape(path));

        for (const auto prefix_len : {std::size_t{2}, std::size_t{4}, std::size_t{8}}) {
            if (path.size() >= prefix_len) {
                prefix_[prefix_len].Add(Prefix(path, prefix_len));
                suffix_[prefix_len].Add(Suffix(path, prefix_len));
            }
        }

        for (const auto& coord : path) {
            x_.Add(coord.x);
            y_.Add(coord.y);
            z_.Add(coord.z);
        }
        for (auto i = std::size_t{1}; i < path.size(); ++i) {
            const auto dx = path[i].x - path[i - 1].x;
            const auto dy = path[i].y - path[i - 1].y;
            const auto dz = path[i].z - path[i - 1].z;
            diff_x_.Add(dx);
            diff_y_.Add(dy);
            diff_z_.Add(dz);
            ++adjacent_pair_count_;
            if (dx >= -1 && dx <= 1 && dy >= -1 && dy <= 1 && dz >= -1 && dz <= 1) {
                ++unit_delta_count_;
            }
            const auto manhattan =
                    std::abs(static_cast<int>(dx)) + std::abs(static_cast<int>(dy))
                    + std::abs(static_cast<int>(dz));
            if (manhattan == 1) {
                ++manhattan_one_count_;
            }
            if (manhattan == 0) {
                ++same_coordinate_consecutive_count_;
            }
        }

        const auto segments = static_cast<std::uint64_t>(SegmentCount(path));
        total_segment_count_ += segments;
        max_segment_count_ = std::max(max_segment_count_, segments);
        if (segments <= 1) {
            ++paths_with_1_segment_or_less_;
        }
        if (segments <= 2) {
            ++paths_with_2_segments_or_less_;
        }
        if (segments <= 4) {
            ++paths_with_4_segments_or_less_;
        }
    }

    [[nodiscard]] qret::Json Json() const {
        auto lengths = length_values_;
        std::sort(lengths.begin(), lengths.end());
        const auto min_length = lengths.empty() ? 0 : lengths.front();
        const auto max_length = lengths.empty() ? 0 : lengths.back();
        const auto sum = std::accumulate(length_values_.begin(), length_values_.end(), std::uint64_t{0});
        const auto mean = length_values_.empty()
                ? 0.0
                : static_cast<double>(sum) / static_cast<double>(length_values_.size());
        auto variance_sum = 0.0;
        for (const auto value : length_values_) {
            const auto diff = static_cast<double>(value) - mean;
            variance_sum += diff * diff;
        }
        const auto stddev = length_values_.empty()
                ? 0.0
                : std::sqrt(variance_sum / static_cast<double>(length_values_.size()));

        auto ret = qret::Json::object();
        ret["path_count"] = path_count_;
        ret["total_coordinate_count"] = total_coordinate_count_;
        ret["length_buckets"] = LengthBucketsJson(length_buckets_);
        ret["length_min"] = min_length;
        ret["length_max"] = max_length;
        ret["length_mean"] = mean;
        ret["length_median"] = Median(lengths);
        ret["length_p75"] = PercentileNearest(lengths, 0.75);
        ret["length_p90"] = PercentileNearest(lengths, 0.90);
        ret["length_p95"] = PercentileNearest(lengths, 0.95);
        ret["length_p99"] = PercentileNearest(lengths, 0.99);
        ret["length_standard_deviation"] = stddev;
        ret["coordinates"] = CoordinateJson();
        ret["duplicates_exact"] = exact_.SummaryJson();
        ret["duplicates_reverse_canonical"] = reverse_.SummaryJson();
        ret["duplicates_relative_shape"] = shape_.SummaryJson();
        ret["prefix_suffix"] = PrefixSuffixJson();
        ret["segments"] = SegmentJson();
        ret["representation_estimates"] = RepresentationEstimates();
        ret["profiler_working_set_estimated_bytes"] = ProfilerWorkingSetBytes();
        return ret;
    }

    [[nodiscard]] const FrequencyCounter& Exact() const {
        return exact_;
    }
    [[nodiscard]] const FrequencyCounter& Reverse() const {
        return reverse_;
    }
    [[nodiscard]] const FrequencyCounter& Shape() const {
        return shape_;
    }
    [[nodiscard]] std::uint64_t PathCount() const {
        return path_count_;
    }
    [[nodiscard]] std::uint64_t TotalCoordinateCount() const {
        return total_coordinate_count_;
    }

private:
    [[nodiscard]] qret::Json CoordinateJson() const {
        auto ret = qret::Json::object();
        ret["x"] = x_.Json();
        ret["y"] = y_.Json();
        ret["z"] = z_.Json();
        ret["dx"] = diff_x_.Json();
        ret["dy"] = diff_y_.Json();
        ret["dz"] = diff_z_.Json();
        ret["adjacent_pair_count"] = adjacent_pair_count_;
        ret["unit_delta_count"] = unit_delta_count_;
        ret["unit_delta_percent"] = Percent(unit_delta_count_, adjacent_pair_count_);
        ret["manhattan_one_count"] = manhattan_one_count_;
        ret["manhattan_one_percent"] = Percent(manhattan_one_count_, adjacent_pair_count_);
        ret["same_coordinate_consecutive_count"] = same_coordinate_consecutive_count_;
        ret["has_consecutive_duplicate_coordinate"] = same_coordinate_consecutive_count_ > 0;
        return ret;
    }

    [[nodiscard]] qret::Json PrefixSuffixJson() const {
        auto ret = qret::Json::object();
        for (const auto length : {std::size_t{2}, std::size_t{4}, std::size_t{8}}) {
            const auto key = fmt::format("length_ge_{}", length);
            ret["prefix"][key] = prefix_.at(length).SummaryJson();
            ret["suffix"][key] = suffix_.at(length).SummaryJson();
        }
        return ret;
    }

    [[nodiscard]] qret::Json SegmentJson() const {
        auto ret = qret::Json::object();
        ret["total_coordinate_count"] = total_coordinate_count_;
        ret["total_segment_count"] = total_segment_count_;
        ret["coordinates_per_segment_mean"] = total_segment_count_ == 0
                ? 0.0
                : static_cast<double>(total_coordinate_count_)
                        / static_cast<double>(total_segment_count_);
        ret["path_count_1_segment_or_less"] = paths_with_1_segment_or_less_;
        ret["path_count_2_segments_or_less"] = paths_with_2_segments_or_less_;
        ret["path_count_4_segments_or_less"] = paths_with_4_segments_or_less_;
        ret["path_percent_1_segment_or_less"] = Percent(paths_with_1_segment_or_less_, path_count_);
        ret["path_percent_2_segments_or_less"] = Percent(paths_with_2_segments_or_less_, path_count_);
        ret["path_percent_4_segments_or_less"] = Percent(paths_with_4_segments_or_less_, path_count_);
        ret["max_segment_count"] = max_segment_count_;
        return ret;
    }

    [[nodiscard]] qret::Json RepresentationEstimates() const {
        const auto coord_size = static_cast<std::uint64_t>(sizeof(Coord3D));
        const auto list_object_bytes =
                path_count_ * static_cast<std::uint64_t>(sizeof(std::list<Coord3D>));
        const auto list_node_unaligned =
                total_coordinate_count_ * ListNodeBytesUnaligned<Coord3D>();
        const auto list_node_aligned = total_coordinate_count_ * ListNodeBytesAligned<Coord3D>();
        const auto current = list_object_bytes + list_node_aligned;
        const auto vector_object_bytes =
                path_count_ * static_cast<std::uint64_t>(sizeof(std::vector<Coord3D>));
        auto vector_next_pow2_payload = std::uint64_t{0};
        auto inline4_overflow = std::uint64_t{0};
        auto inline8_overflow = std::uint64_t{0};
        for (const auto length : length_values_) {
            vector_next_pow2_payload += NextPowerOfTwo(length) * coord_size;
            inline4_overflow += length > 4 ? (length - 4) * coord_size : 0;
            inline8_overflow += length > 8 ? (length - 8) * coord_size : 0;
        }
        const auto vector_exact = vector_object_bytes + total_coordinate_count_ * coord_size;
        const auto vector_next_pow2 = vector_object_bytes + vector_next_pow2_payload;
        const auto offset_length_bytes =
                path_count_ * static_cast<std::uint64_t>(2 * sizeof(std::uint32_t));
        const auto exact_unique_path_table =
                exact_.UniqueCount() * static_cast<std::uint64_t>(2 * sizeof(std::uint32_t));
        const auto exact_shared = exact_.UniqueCoordinateCount() * coord_size
                + exact_unique_path_table
                + path_count_ * static_cast<std::uint64_t>(sizeof(std::uint32_t));
        const auto reverse_shared = reverse_.UniqueCoordinateCount() * coord_size
                + reverse_.UniqueCount() * static_cast<std::uint64_t>(2 * sizeof(std::uint32_t))
                + path_count_ * static_cast<std::uint64_t>(sizeof(std::uint32_t) + sizeof(bool));
        const auto shape_shared = shape_.UniqueCoordinateCount() * coord_size
                + shape_.UniqueCount() * static_cast<std::uint64_t>(2 * sizeof(std::uint32_t))
                + path_count_ * static_cast<std::uint64_t>(sizeof(Coord3D) + sizeof(std::uint32_t));
        const auto segment_bytes =
                path_count_ * static_cast<std::uint64_t>(sizeof(Coord3D) + 2 * sizeof(std::uint32_t))
                + total_segment_count_ * static_cast<std::uint64_t>(8);
        const auto inline4_object =
                path_count_
                * static_cast<std::uint64_t>(
                        sizeof(std::size_t) + 4 * sizeof(Coord3D) + 3 * sizeof(void*)
                );
        const auto inline8_object =
                path_count_
                * static_cast<std::uint64_t>(
                        sizeof(std::size_t) + 8 * sizeof(Coord3D) + 3 * sizeof(void*)
                );

        auto rows = qret::Json::array();
        const auto add = [&](std::string_view name,
                             std::uint64_t bytes,
                             std::string_view semantic_risk,
                             std::string_view implementation_risk) {
            auto row = qret::Json::object();
            row["representation"] = name;
            row["estimated_bytes"] = bytes;
            row["saving_bytes"] = SaturatingSub(current, bytes);
            row["saving_percent"] = current == 0 ? 0.0 : Percent(SaturatingSub(current, bytes), current);
            row["semantic_risk"] = semantic_risk;
            row["implementation_risk"] = implementation_risk;
            rows.emplace_back(std::move(row));
        };
        add("std::list<Coord3D> current aligned estimate", current, "none", "none");
        add("std::vector<Coord3D> capacity==size", vector_exact, "low", "low");
        add("std::vector<Coord3D> next-power-of-two capacity", vector_next_pow2, "low", "low");
        add("inline4 + overflow vector", inline4_object + inline4_overflow, "low", "medium");
        add("inline8 + overflow vector", inline8_object + inline8_overflow, "low", "medium");
        add("flat pool + offset no sharing", total_coordinate_count_ * coord_size + offset_length_bytes, "low", "medium");
        add("flat pool + exact path interning", exact_shared, "low", "medium");
        add("flat pool + reverse canonical interning", reverse_shared, "medium", "medium");
        add("relative shape pool + origin", shape_shared, "medium", "high");
        add("segment representation", segment_bytes, "medium", "high");

        auto ret = qret::Json::object();
        ret["current_list_object_bytes"] = list_object_bytes;
        ret["current_list_node_bytes_unaligned"] = list_node_unaligned;
        ret["current_list_node_bytes_aligned"] = list_node_aligned;
        ret["current_list_aligned_bytes"] = current;
        ret["rows"] = rows;
        return ret;
    }

    [[nodiscard]] std::uint64_t ProfilerWorkingSetBytes() const {
        const auto coord_size = static_cast<std::uint64_t>(sizeof(Coord3D));
        return (exact_.UniqueCoordinateCount() + reverse_.UniqueCoordinateCount()
                + shape_.UniqueCoordinateCount())
                * coord_size;
    }

    std::uint64_t path_count_ = 0;
    std::uint64_t total_coordinate_count_ = 0;
    std::vector<std::uint64_t> length_values_;
    std::map<std::string, std::uint64_t> length_buckets_;
    AxisStats x_;
    AxisStats y_;
    AxisStats z_;
    AxisStats diff_x_;
    AxisStats diff_y_;
    AxisStats diff_z_;
    std::uint64_t adjacent_pair_count_ = 0;
    std::uint64_t unit_delta_count_ = 0;
    std::uint64_t manhattan_one_count_ = 0;
    std::uint64_t same_coordinate_consecutive_count_ = 0;
    std::uint64_t total_segment_count_ = 0;
    std::uint64_t max_segment_count_ = 0;
    std::uint64_t paths_with_1_segment_or_less_ = 0;
    std::uint64_t paths_with_2_segments_or_less_ = 0;
    std::uint64_t paths_with_4_segments_or_less_ = 0;
    FrequencyCounter exact_;
    FrequencyCounter reverse_;
    FrequencyCounter shape_;
    std::map<std::size_t, FrequencyCounter> prefix_{
            {2, FrequencyCounter()},
            {4, FrequencyCounter()},
            {8, FrequencyCounter()},
    };
    std::map<std::size_t, FrequencyCounter> suffix_{
            {2, FrequencyCounter()},
            {4, FrequencyCounter()},
            {8, FrequencyCounter()},
    };
};

struct MagicOperandStats {
    std::uint64_t instruction_count = 0;
    std::uint64_t qtarget_elements = 0;
    std::uint64_t basis_elements = 0;
    std::uint64_t condition_elements = 0;
    std::uint64_t ccreate_elements = 0;
    std::uint64_t mtarget_elements = 0;
};

qret::Json MagicOperandStatsJson(const MagicOperandStats& stats, const PathProfileAccumulator& paths) {
    const auto q_node = ListNodeBytesUnaligned<QSymbol>();
    const auto basis_node = ListNodeBytesUnaligned<Pauli>();
    const auto condition_node = ListNodeBytesUnaligned<CSymbol>();
    const auto c_node = ListNodeBytesUnaligned<CSymbol>();
    const auto m_node = ListNodeBytesUnaligned<MSymbol>();
    const auto coord_node = ListNodeBytesUnaligned<Coord3D>();
    const auto coord_node_aligned = ListNodeBytesAligned<Coord3D>();
    const auto path_coords = paths.TotalCoordinateCount();

    auto ret = qret::Json::object();
    ret["instruction_count"] = stats.instruction_count;
    ret["sizeof_lattice_surgery_magic"] = sizeof(LatticeSurgeryMagic);
    ret["sizeof_coord3d"] = sizeof(Coord3D);
    ret["sizeof_list_coord3d"] = sizeof(std::list<Coord3D>);
    ret["sizeof_qsymbol"] = sizeof(QSymbol);
    ret["sizeof_csymbol"] = sizeof(CSymbol);
    ret["sizeof_msymbol"] = sizeof(MSymbol);
    ret["sizeof_pauli"] = sizeof(Pauli);
    ret["sizeof_metadata"] = sizeof(ScLsMetadata);
    ret["magic_instruction_object_bytes_estimated"] =
            stats.instruction_count * static_cast<std::uint64_t>(sizeof(LatticeSurgeryMagic));
    ret["magic_metadata_bytes_in_instruction_object"] =
            stats.instruction_count * static_cast<std::uint64_t>(sizeof(ScLsMetadata));
    ret["list_node_model"] = {
            {"coord3d_unaligned_bytes", coord_node},
            {"coord3d_aligned_bytes", coord_node_aligned},
            {"coord3d_pointer_overhead_bytes", 2 * sizeof(void*)},
            {"standard_layout_exact", false},
    };

    ret["qtarget_elements"] = stats.qtarget_elements;
    ret["basis_elements"] = stats.basis_elements;
    ret["condition_elements"] = stats.condition_elements;
    ret["ccreate_elements"] = stats.ccreate_elements;
    ret["mtarget_elements"] = stats.mtarget_elements;
    ret["path_coordinate_elements"] = path_coords;
    ret["qtarget_list_node_bytes_estimated"] = stats.qtarget_elements * q_node;
    ret["basis_list_node_bytes_estimated"] = stats.basis_elements * basis_node;
    ret["condition_list_node_bytes_estimated"] = stats.condition_elements * condition_node;
    ret["ccreate_list_node_bytes_estimated"] = stats.ccreate_elements * c_node;
    ret["mtarget_list_node_bytes_estimated"] = stats.mtarget_elements * m_node;
    ret["path_coord_payload_bytes"] =
            path_coords * static_cast<std::uint64_t>(sizeof(Coord3D));
    ret["path_list_node_pointer_overhead_bytes"] = path_coords * static_cast<std::uint64_t>(2 * sizeof(void*));
    ret["path_list_node_allocator_alignment_overhead_estimated"] =
            path_coords * SaturatingSub(coord_node_aligned, coord_node);
    ret["path_list_node_bytes_unaligned_estimated"] = path_coords * coord_node;
    ret["path_list_node_bytes_aligned_estimated"] = path_coords * coord_node_aligned;
    ret["path_list_object_bytes_in_instruction_object"] =
            stats.instruction_count * static_cast<std::uint64_t>(sizeof(std::list<Coord3D>));
    ret["operand_list_node_bytes_unaligned_estimated"] =
            stats.qtarget_elements * q_node + stats.basis_elements * basis_node
            + stats.condition_elements * condition_node + stats.ccreate_elements * c_node
            + stats.mtarget_elements * m_node + path_coords * coord_node;
    ret["operand_list_node_bytes_aligned_path_estimated"] =
            stats.qtarget_elements * q_node + stats.basis_elements * basis_node
            + stats.condition_elements * condition_node + stats.ccreate_elements * c_node
            + stats.mtarget_elements * m_node + path_coords * coord_node_aligned;
    ret["operand_list_object_bytes_in_instruction_object_estimated"] =
            stats.instruction_count
            * static_cast<std::uint64_t>(
                    sizeof(std::list<CSymbol>) + sizeof(std::list<QSymbol>)
                    + sizeof(std::list<Pauli>) + sizeof(std::list<Coord3D>)
                    + sizeof(std::list<CSymbol>) + sizeof(std::list<MSymbol>)
            );
    return ret;
}

qret::Json AllMachinePathBytesJson(const std::map<std::string, std::uint64_t>& coord_count) {
    auto by_type = qret::Json::object();
    auto cnot_bytes = std::uint64_t{0};
    auto magic_bytes = std::uint64_t{0};
    auto other_bytes = std::uint64_t{0};
    auto total_bytes = std::uint64_t{0};
    for (const auto& [type, count] : coord_count) {
        const auto bytes = count * ListNodeBytesUnaligned<Coord3D>();
        auto row = qret::Json::object();
        row["coordinate_count"] = count;
        row["list_node_bytes_unaligned_estimated"] = bytes;
        row["list_node_bytes_aligned_estimated"] = count * ListNodeBytesAligned<Coord3D>();
        by_type[type] = std::move(row);
        total_bytes += bytes;
        if (type == "CNOT") {
            cnot_bytes += bytes;
        } else if (type == "LATTICE_SURGERY_MAGIC") {
            magic_bytes += bytes;
        } else {
            other_bytes += bytes;
        }
    }
    auto ret = qret::Json::object();
    ret["by_instruction_type"] = by_type;
    ret["lattice_surgery_magic_ancilla_path_bytes"] = magic_bytes;
    ret["cnot_ancilla_path_bytes"] = cnot_bytes;
    ret["other_instruction_ancilla_path_bytes"] = other_bytes;
    ret["all_ancilla_path_bytes"] = total_bytes;
    return ret;
}
}  // namespace

bool MagicPathProfilingEnabled() {
    const auto* raw = std::getenv("QRET_PROFILE_MAGIC_PATHS");
    if (raw == nullptr || std::string(raw).empty() || std::string(raw) == "0") {
        return false;
    }
    if (std::string(raw) == "1") {
        return true;
    }
    throw std::invalid_argument("QRET_PROFILE_MAGIC_PATHS must be 0 or 1");
}

qret::Json MagicPathProfileForPathsForTest(
        const std::vector<std::list<Coord3D>>& paths,
        bool force_hash_collision
) {
    auto accumulator = PathProfileAccumulator(force_hash_collision);
    for (const auto& path : paths) {
        accumulator.AddPath(path);
    }
    return accumulator.Json();
}

qret::Json LatticeSurgeryMagicPathMemoryProfile(const qret::MachineFunction& mf) {
    auto paths = PathProfileAccumulator();
    auto operand_stats = MagicOperandStats();
    auto all_path_coord_count = std::map<std::string, std::uint64_t>();

    for (const auto& mbb : mf) {
        for (const auto& minst : mbb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            const auto type_name = std::string(ToString(inst.Type()));
            all_path_coord_count[type_name] += static_cast<std::uint64_t>(inst.Ancilla().size());
            if (inst.Type() != ScLsInstructionType::LATTICE_SURGERY_MAGIC) {
                continue;
            }
            const auto& magic = static_cast<const LatticeSurgeryMagic&>(inst);
            ++operand_stats.instruction_count;
            operand_stats.qtarget_elements += static_cast<std::uint64_t>(magic.QTarget().size());
            operand_stats.basis_elements += static_cast<std::uint64_t>(magic.BasisList().size());
            operand_stats.condition_elements += static_cast<std::uint64_t>(magic.Condition().size());
            operand_stats.ccreate_elements += static_cast<std::uint64_t>(magic.CCreate().size());
            operand_stats.mtarget_elements += static_cast<std::uint64_t>(magic.MTarget().size());
            paths.AddPath(magic.Path());
        }
    }

    auto ret = paths.Json();
    ret["profile_schema"] = "qret_lattice_surgery_magic_path_memory_v1";
    ret["scope"] = "LATTICE_SURGERY_MAGIC";
    ret["magic_operand_memory"] = MagicOperandStatsJson(operand_stats, paths);
    ret["all_machine_ancilla_path_memory"] = AllMachinePathBytesJson(all_path_coord_count);
    ret["observed_vs_estimated_note"] =
            "counts are observed; byte totals are sizeof/list-node allocator estimates; "
            "std::list node layout is not specified by the C++ standard";
    return ret;
}

void MaybeWriteLatticeSurgeryMagicPathProfile(
        const qret::MachineFunction& mf,
        std::string_view stage
) {
    if (!MagicPathProfilingEnabled()) {
        return;
    }
    auto profile = LatticeSurgeryMagicPathMemoryProfile(mf);
    profile["profile_stage"] = stage;

    const auto* output_path = std::getenv("QRET_MAGIC_PATH_PROFILE_JSON");
    if (output_path != nullptr && !std::string(output_path).empty()) {
        auto out = std::ofstream(output_path);
        if (!out) {
            throw std::runtime_error(fmt::format(
                    "failed to open QRET_MAGIC_PATH_PROFILE_JSON '{}'",
                    output_path
            ));
        }
        out << profile.dump(2) << '\n';
    }
    qret::rss_profile::Mark("magic_path_profile", profile);
}

std::size_t MagicPathSegmentCountForTest(const std::list<Coord3D>& path) {
    return SegmentCount(ToVector(path));
}
}  // namespace qret::sc_ls_fixed_v0
