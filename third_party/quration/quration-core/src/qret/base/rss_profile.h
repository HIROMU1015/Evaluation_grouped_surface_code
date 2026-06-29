/**
 * @file qret/base/rss_profile.h
 * @brief Profiling-only RSS markers for qret subprocess memory diagnosis.
 */

#ifndef QRET_BASE_RSS_PROFILE_H
#define QRET_BASE_RSS_PROFILE_H

#include <string_view>

#include "qret/base/json.h"
#include "qret/qret_export.h"

namespace qret::rss_profile {
QRET_EXPORT bool Enabled();
QRET_EXPORT bool HighWaterEnabled();
QRET_EXPORT void Mark(std::string_view stage);
QRET_EXPORT void Mark(std::string_view stage, const qret::Json& extra);
QRET_EXPORT bool DiagnosticTrimRequested(std::string_view stage);
QRET_EXPORT void MaybeDiagnosticTrim(std::string_view stage);
}  // namespace qret::rss_profile

#endif  // QRET_BASE_RSS_PROFILE_H
