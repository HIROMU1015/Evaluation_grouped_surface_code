/**
 * @file qret/base/rss_profile.cpp
 * @brief Profiling-only RSS markers for qret subprocess memory diagnosis.
 */

#include "qret/base/rss_profile.h"

#include <sys/types.h>
#include <unistd.h>

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>

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
            ret["smaps_rss_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "Pss:"); value.has_value()) {
            ret["smaps_pss_kb"] = *value;
        } else if (auto value = ParseKbLine(line, "Private_Dirty:"); value.has_value()) {
            ret["smaps_private_dirty_kb"] = *value;
        }
    }
    return ret;
}
}  // namespace

bool Enabled() {
    return OutputPath().has_value();
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
}  // namespace qret::rss_profile
