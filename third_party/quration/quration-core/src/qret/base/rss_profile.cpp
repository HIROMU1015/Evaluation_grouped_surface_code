/**
 * @file qret/base/rss_profile.cpp
 * @brief Profiling-only RSS markers for qret subprocess memory diagnosis.
 */

#include "qret/base/rss_profile.h"

#include <fmt/format.h>

#if defined(__GLIBC__)
#include <malloc.h>
#endif

#include <sys/types.h>
#include <sys/resource.h>
#include <unistd.h>

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <sstream>
#include <string>
#include <string_view>

namespace qret::rss_profile {
namespace {
const auto ProcessStart = std::chrono::steady_clock::now();
std::mutex WriteMutex;

std::optional<std::string> OutputPath() {
    const auto* raw = std::getenv("QRET_RSS_PROFILE_JSONL");
    if (raw == nullptr || std::string(raw).empty()) {
        return std::nullopt;
    }
    return std::string(raw);
}

std::optional<std::int64_t> ParseKbLine(const std::string& line, const std::string& key) {
    if (!line.starts_with(key)) {
        return std::nullopt;
    }
    auto rest = line.substr(key.size());
    auto in = std::istringstream(rest);
    auto value = std::int64_t{0};
    in >> value;
    if (!in) {
        return std::nullopt;
    }
    return value;
}

qret::Json ReadProcStatus() {
    auto ret = qret::Json::object();
    auto in = std::ifstream("/proc/self/status");
    if (!in) {
        return ret;
    }

    auto line = std::string();
    while (std::getline(in, line)) {
        if (auto value = ParseKbLine(line, "VmRSS:"); value.has_value()) {
            ret["vmrss_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "VmHWM:"); value.has_value()) {
            ret["vmhwm_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "VmSize:"); value.has_value()) {
            ret["vmsize_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "VmData:"); value.has_value()) {
            ret["vmdata_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "RssAnon:"); value.has_value()) {
            ret["rss_anon_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "RssFile:"); value.has_value()) {
            ret["rss_file_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "RssShmem:"); value.has_value()) {
            ret["rss_shmem_kb"] = *value;
        }
    }
    return ret;
}

qret::Json ReadProcSmapsRollup() {
    auto ret = qret::Json::object();
    auto in = std::ifstream("/proc/self/smaps_rollup");
    if (!in) {
        return ret;
    }

    auto line = std::string();
    while (std::getline(in, line)) {
        if (auto value = ParseKbLine(line, "Rss:"); value.has_value()) {
            ret["smaps_rollup_rss_kb"] = *value;
            ret["smaps_rss_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "Pss:"); value.has_value()) {
            ret["pss_kb"] = *value;
            ret["smaps_pss_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "Private_Dirty:"); value.has_value()) {
            ret["private_dirty_kb"] = *value;
            ret["smaps_private_dirty_kb"] = *value;
        }
    }
    return ret;
}

qret::Json ReadResourceUsage() {
    auto ret = qret::Json::object();
    auto usage = rusage{};
    if (getrusage(RUSAGE_SELF, &usage) == 0) {
        ret["ru_maxrss_kb"] = static_cast<std::int64_t>(usage.ru_maxrss);
    }
    return ret;
}

qret::Json ReadMallinfo2() {
    auto ret = qret::Json::object();
#if defined(__GLIBC__)
    const auto info = mallinfo2();
    ret["mallinfo2_supported"] = true;
    ret["mallinfo2_arena"] = static_cast<std::uint64_t>(info.arena);
    ret["mallinfo2_ordblks"] = static_cast<std::uint64_t>(info.ordblks);
    ret["mallinfo2_hblkhd"] = static_cast<std::uint64_t>(info.hblkhd);
    ret["mallinfo2_uordblks"] = static_cast<std::uint64_t>(info.uordblks);
    ret["mallinfo2_fordblks"] = static_cast<std::uint64_t>(info.fordblks);
    ret["mallinfo2_keepcost"] = static_cast<std::uint64_t>(info.keepcost);
    ret["mallinfo2_uordblks_kb"] = static_cast<std::uint64_t>(info.uordblks / 1024);
    ret["mallinfo2_fordblks_kb"] = static_cast<std::uint64_t>(info.fordblks / 1024);
#else
    ret["mallinfo2_supported"] = false;
#endif
    return ret;
}

std::string DiagnosticTrimMode() {
    const auto* raw = std::getenv("QRET_RSS_DIAGNOSTIC_TRIM_STAGE");
    if (raw == nullptr || std::string(raw).empty()) {
        return "none";
    }
    const auto mode = std::string(raw);
    if (mode == "none" || mode == "after_json_dom_destroy"
        || mode == "after_routing_temporary_destroy"
        || mode == "after_machine_function_construction" || mode == "after_mapping"
        || mode == "routing_after_inverse_map_release" || mode == "after_compile_info"
        || mode == "both") {
        return mode;
    }
    throw std::invalid_argument(
            "QRET_RSS_DIAGNOSTIC_TRIM_STAGE must be one of none, "
            "after_json_dom_destroy, after_routing_temporary_destroy, "
            "after_machine_function_construction, after_mapping, "
            "routing_after_inverse_map_release, after_compile_info, or both"
    );
}
}  // namespace

bool Enabled() {
    return OutputPath().has_value();
}

bool HighWaterEnabled() {
    const auto* raw = std::getenv("QRET_PROFILE_HIGH_WATER");
    if (raw == nullptr || std::string(raw).empty() || std::string(raw) == "0") {
        return false;
    }
    if (std::string(raw) == "1") {
        return Enabled();
    }
    throw std::invalid_argument("QRET_PROFILE_HIGH_WATER must be 0 or 1");
}

void Mark(std::string_view stage) {
    Mark(stage, qret::Json::object());
}

void Mark(std::string_view stage, const qret::Json& extra) {
    const auto output_path = OutputPath();
    if (!output_path.has_value()) {
        return;
    }

    auto payload = qret::Json::object();
    payload["schema"] = "qret_rss_profile_v1";
    payload["pid"] = static_cast<std::int64_t>(getpid());
    payload["stage"] = std::string(stage);
    payload["elapsed_sec"] = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - ProcessStart
    ).count();

    auto status = ReadProcStatus();
    for (auto it = status.begin(); it != status.end(); ++it) {
        payload[it.key()] = it.value();
    }
    auto smaps = ReadProcSmapsRollup();
    for (auto it = smaps.begin(); it != smaps.end(); ++it) {
        payload[it.key()] = it.value();
    }
    auto usage = ReadResourceUsage();
    for (auto it = usage.begin(); it != usage.end(); ++it) {
        payload[it.key()] = it.value();
    }
    auto heap = ReadMallinfo2();
    for (auto it = heap.begin(); it != heap.end(); ++it) {
        payload[it.key()] = it.value();
    }
    if (!extra.empty()) {
        payload["extra"] = extra;
    }

    try {
        std::lock_guard<std::mutex> lock(WriteMutex);
        auto out = std::ofstream(*output_path, std::ios::app);
        if (out) {
            out << payload.dump() << '\n';
        }
    } catch (...) {
        // Profiling must never change compile behavior.
    }
}

bool DiagnosticTrimRequested(const std::string_view stage) {
    const auto mode = DiagnosticTrimMode();
    if (mode == "none") {
        return false;
    }
    if (mode == "both") {
        return stage == "after_json_dom_destroy"
                || stage == "after_routing_temporary_destroy"
                || stage == "after_machine_function_construction" || stage == "after_mapping"
                || stage == "routing_after_inverse_map_release"
                || stage == "after_compile_info";
    }
    return mode == stage;
}

void MaybeDiagnosticTrim(const std::string_view stage) {
    if (!DiagnosticTrimRequested(stage)) {
        return;
    }
    auto extra = qret::Json::object();
    extra["trim_stage"] = std::string(stage);
#if defined(__GLIBC__)
    extra["glibc_malloc_trim_supported"] = true;
    Mark(fmt::format("diagnostic_trim_before_{}", stage), extra);
    const auto start = std::chrono::steady_clock::now();
    const auto result = malloc_trim(0);
    const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start)
                                 .count();
    extra["malloc_trim_return"] = result;
    extra["malloc_trim_elapsed_sec"] = elapsed;
    Mark(fmt::format("diagnostic_trim_after_{}", stage), extra);
#else
    extra["glibc_malloc_trim_supported"] = false;
    Mark(fmt::format("diagnostic_trim_unsupported_{}", stage), extra);
    throw std::runtime_error("QRET_RSS_DIAGNOSTIC_TRIM_STAGE requires glibc malloc_trim support");
#endif
}
}  // namespace qret::rss_profile
