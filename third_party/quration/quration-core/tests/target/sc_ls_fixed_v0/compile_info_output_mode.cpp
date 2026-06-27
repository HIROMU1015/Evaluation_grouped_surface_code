#include "qret/target/sc_ls_fixed_v0/compile_info.h"

#include <gtest/gtest.h>

#include <array>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

#include "qret/base/json.h"
#include "qret/base/string.h"
#include "qret/target/sc_ls_fixed_v0/topology.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
constexpr auto TimeSeriesKeys = std::array{
        "gate_throughput",
        "measurement_feedback_rate",
        "magic_state_consumption_rate",
        "entanglement_consumption_rate",
        "chip_cell_algorithmic_qubit",
        "chip_cell_algorithmic_qubit_ratio",
        "chip_cell_active_qubit_area",
        "chip_cell_active_qubit_area_ratio",
};

std::shared_ptr<const Topology> LoadPlaneTopologyFixture() {
    for (const auto& path : {
                 std::filesystem::path("quration-core/tests/data/topology/plane.yaml"),
                 std::filesystem::path(
                         "third_party/quration/quration-core/tests/data/topology/plane.yaml"
                 ),
         }) {
        if (std::filesystem::exists(path)) {
            return Topology::FromYAML(qret::LoadFile(path.string()));
        }
    }
    throw std::runtime_error("failed to find plane topology fixture");
}

ScLsFixedV0CompileInfo BuildCompileInfo(bool with_topology) {
    auto info = ScLsFixedV0CompileInfo();
    info.magic_generation_period = 15;
    info.maximum_magic_state_stock = 10000;
    info.entanglement_generation_period = 100;
    info.maximum_entangled_state_stock = 10;
    info.reaction_time = 1;
    if (with_topology) {
        info.topology = LoadPlaneTopologyFixture();
    }
    info.runtime = 3;
    info.runtime_without_topology = 2;
    info.gate_count = 11;
    info.gate_count_dict[ScLsInstructionType::HADAMARD] = 5;
    info.gate_depth = 7;
    info.gate_throughput = {1, 3, 5};
    info.measurement_feedback_count = 2;
    info.measurement_feedback_depth = 1;
    info.measurement_feedback_rate = {0, 2, 4};
    info.runtime_estimation_measurement_feedback_count = 2;
    info.runtime_estimation_measurement_feedback_depth = 1;
    info.magic_state_consumption_count = 4;
    info.magic_state_consumption_depth = 2;
    info.magic_state_consumption_rate = {0, 1, 2};
    info.runtime_estimation_magic_state_consumption_count = 60;
    info.runtime_estimation_magic_state_consumption_depth = 30;
    info.magic_factory_count = 4;
    info.entanglement_consumption_count = 6;
    info.entanglement_consumption_depth = 3;
    info.entanglement_consumption_rate = {0, 3, 6};
    info.runtime_estimation_entanglement_consumption_count = 600;
    info.runtime_estimation_entanglement_consumption_depth = 300;
    info.entanglement_factory_count = 1;
    info.chip_cell_count = 96;
    info.chip_cell_algorithmic_qubit = {8, 10, 12};
    info.chip_cell_algorithmic_qubit_ratio = {0.25, 0.5, 0.75};
    info.chip_cell_active_qubit_area = {9, 11, 13};
    info.chip_cell_active_qubit_area_ratio = {0.125, 0.25, 0.5};
    info.qubit_volume = 123;
    info.code_distance = 5;
    info.execution_time_sec = 1.25;
    info.num_physical_qubits = 200;
    return info;
}
}  // namespace

TEST(CompileInfoOutputMode, DefaultJsonIsFull) {
    const auto info = BuildCompileInfo(false);
    const auto default_json = info.Json();
    const auto full_json = info.Json(CompileInfoOutputMode::Full);

    EXPECT_EQ(default_json, full_json);
    for (const auto* key : TimeSeriesKeys) {
        EXPECT_TRUE(full_json.contains(key)) << key;
        EXPECT_TRUE(full_json.contains(std::string(key) + "_ave")) << key;
        EXPECT_TRUE(full_json.contains(std::string(key) + "_peak")) << key;
    }
}

TEST(CompileInfoOutputMode, SummaryOmitsFullArraysAndKeepsStatsAndScalars) {
    const auto info = BuildCompileInfo(true);
    const auto full_json = info.Json(CompileInfoOutputMode::Full);
    const auto summary_json = info.Json(CompileInfoOutputMode::Summary);

    EXPECT_TRUE(summary_json.contains("topology"));
    EXPECT_EQ(summary_json["runtime"], full_json["runtime"]);
    EXPECT_EQ(summary_json["runtime_without_topology"], full_json["runtime_without_topology"]);
    EXPECT_EQ(summary_json["gate_count"], full_json["gate_count"]);
    EXPECT_EQ(summary_json["gate_count_detail"], full_json["gate_count_detail"]);
    EXPECT_EQ(summary_json["gate_depth"], full_json["gate_depth"]);
    EXPECT_EQ(summary_json["qubit_volume"], full_json["qubit_volume"]);
    EXPECT_EQ(summary_json["code_distance"], full_json["code_distance"]);
    EXPECT_EQ(summary_json["execution_time_sec"], full_json["execution_time_sec"]);
    EXPECT_EQ(summary_json["num_physical_qubits"], full_json["num_physical_qubits"]);

    for (const auto* key : TimeSeriesKeys) {
        EXPECT_TRUE(full_json.contains(key)) << key;
        EXPECT_FALSE(summary_json.contains(key)) << key;
        EXPECT_EQ(summary_json[std::string(key) + "_ave"], full_json[std::string(key) + "_ave"])
                << key;
        EXPECT_EQ(summary_json[std::string(key) + "_peak"], full_json[std::string(key) + "_peak"])
                << key;
    }
}

TEST(CompileInfoOutputMode, SummaryCannotBeReadAsFullCompileInfo) {
    const auto info = BuildCompileInfo(false);
    const auto summary_json = info.Json(CompileInfoOutputMode::Summary);

    auto parsed = ScLsFixedV0CompileInfo();
    EXPECT_THROW(from_json(summary_json, parsed), nlohmann::json::exception);
}

TEST(CompileInfoOutputMode, EmptySingleElementAndFloatingStats) {
    auto info = BuildCompileInfo(false);
    info.gate_throughput = {};
    info.measurement_feedback_rate = {7};
    info.chip_cell_algorithmic_qubit_ratio = {0.25, 0.75};

    const auto summary_json = info.Json(CompileInfoOutputMode::Summary);
    EXPECT_DOUBLE_EQ(summary_json["gate_throughput_ave"].get<double>(), 0.0);
    EXPECT_EQ(summary_json["gate_throughput_peak"].get<std::uint64_t>(), 0);
    EXPECT_DOUBLE_EQ(summary_json["measurement_feedback_rate_ave"].get<double>(), 7.0);
    EXPECT_EQ(summary_json["measurement_feedback_rate_peak"].get<std::uint64_t>(), 7);
    EXPECT_DOUBLE_EQ(summary_json["chip_cell_algorithmic_qubit_ratio_ave"].get<double>(), 0.5);
    EXPECT_DOUBLE_EQ(summary_json["chip_cell_algorithmic_qubit_ratio_peak"].get<double>(), 0.75);
}

TEST(CompileInfoOutputMode, InvalidModeThrows) {
    EXPECT_EQ(CompileInfoOutputModeFromString("full"), CompileInfoOutputMode::Full);
    EXPECT_EQ(CompileInfoOutputModeFromString("summary"), CompileInfoOutputMode::Summary);
    EXPECT_THROW(CompileInfoOutputModeFromString("compact"), std::invalid_argument);
}
}  // namespace qret::sc_ls_fixed_v0
