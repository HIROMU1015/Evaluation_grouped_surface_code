#include "qret/target/sc_ls_fixed_v0/compile_info.h"

#include <gtest/gtest.h>

#include <array>
#include <cstdint>
#include <filesystem>
#include <limits>
#include <sstream>
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

template <typename T>
TimeSeriesSummaryStats<T> StatsFromVector(const std::vector<T>& values) {
    auto stats = TimeSeriesSummaryStats<T>();
    for (const auto& value : values) {
        stats.Add(value);
    }
    return stats;
}

ScLsFixedV0CompileInfo BuildFullCompileInfo(bool with_topology) {
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
    info.gate_count_dict[ScLsInstructionType::LATTICE_SURGERY] = 6;
    info.gate_depth = 7;
    info.gate_throughput = {5, 1, 5};
    info.measurement_feedback_count = 2;
    info.measurement_feedback_depth = 1;
    info.measurement_feedback_rate = {4, 0, 2};
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
    info.entanglement_consumption_rate = {0, 6, 3};
    info.runtime_estimation_entanglement_consumption_count = 600;
    info.runtime_estimation_entanglement_consumption_depth = 300;
    info.entanglement_factory_count = 1;
    info.chip_cell_count = 96;
    info.chip_cell_algorithmic_qubit = {8, 12, 10};
    info.chip_cell_algorithmic_qubit_ratio = {0.25, 0.75, 0.5};
    info.chip_cell_active_qubit_area = {9, 13, 11};
    info.chip_cell_active_qubit_area_ratio = {0.125, 0.5, 0.25};
    info.qubit_volume = 33;
    info.code_distance = 5;
    info.execution_time_sec = 1.25;
    info.num_physical_qubits = 200;
    return info;
}

ScLsFixedV0CompileInfo BuildAggregateCompileInfo(bool with_topology) {
    auto info = BuildFullCompileInfo(with_topology);
    info.gate_throughput_summary = StatsFromVector(info.gate_throughput);
    info.measurement_feedback_rate_summary = StatsFromVector(info.measurement_feedback_rate);
    info.magic_state_consumption_rate_summary =
            StatsFromVector(info.magic_state_consumption_rate);
    info.entanglement_consumption_rate_summary =
            StatsFromVector(info.entanglement_consumption_rate);
    info.chip_cell_algorithmic_qubit_summary =
            StatsFromVector(info.chip_cell_algorithmic_qubit);
    info.chip_cell_algorithmic_qubit_ratio_summary =
            StatsFromVector(info.chip_cell_algorithmic_qubit_ratio);
    info.chip_cell_active_qubit_area_summary =
            StatsFromVector(info.chip_cell_active_qubit_area);
    info.chip_cell_active_qubit_area_ratio_summary =
            StatsFromVector(info.chip_cell_active_qubit_area_ratio);
    info.gate_throughput = {};
    info.measurement_feedback_rate = {};
    info.magic_state_consumption_rate = {};
    info.entanglement_consumption_rate = {};
    info.chip_cell_algorithmic_qubit = {};
    info.chip_cell_algorithmic_qubit_ratio = {};
    info.chip_cell_active_qubit_area = {};
    info.chip_cell_active_qubit_area_ratio = {};
    return info;
}

template <typename T>
void ExpectStatsMatchVector(const std::vector<T>& values) {
    const auto stats = StatsFromVector(values);
    const auto [vector_ave, vector_peak] = ScLsFixedV0CompileInfo::CalcAveAndPeak(values);
    const auto [stats_ave, stats_peak] = stats.AveAndPeak();
    EXPECT_DOUBLE_EQ(stats_ave, vector_ave);
    EXPECT_EQ(stats_peak, vector_peak);
}
}  // namespace

TEST(TimeSeriesSummaryStats, EmptyInputMatchesVectorFallback) {
    const auto stats = TimeSeriesSummaryStats<std::uint64_t>();
    const auto [ave, peak] = stats.AveAndPeak();
    EXPECT_DOUBLE_EQ(ave, 0.0);
    EXPECT_EQ(peak, 0U);
}

TEST(TimeSeriesSummaryStats, IntegerInputsMatchCalcAveAndPeak) {
    ExpectStatsMatchVector<std::uint64_t>({7});
    ExpectStatsMatchVector<std::uint64_t>({0, 0, 0});
    ExpectStatsMatchVector<std::uint64_t>({1, 3, 5, 7});
    ExpectStatsMatchVector<std::uint64_t>({9, 1, 3});
    ExpectStatsMatchVector<std::uint64_t>({1, 9, 3});
    ExpectStatsMatchVector<std::uint64_t>({1, 3, 9});
    ExpectStatsMatchVector<std::uint64_t>({4, 4, 4});
}

TEST(TimeSeriesSummaryStats, LargeIntegerValuesUseExistingUnsignedSumRules) {
    const auto values =
            std::vector<std::uint64_t>{std::numeric_limits<std::uint64_t>::max(), 1};
    ExpectStatsMatchVector(values);
}

TEST(TimeSeriesSummaryStats, FloatingRatioInputsMatchCalcAveAndPeak) {
    ExpectStatsMatchVector<double>({0.25, 0.75, 0.5});
    ExpectStatsMatchVector<double>({0.0, 0.0, 0.0});
}

TEST(TimeSeriesSummaryStats, CountOverflowGuard) {
    auto stats = TimeSeriesSummaryStats<std::uint64_t>();
    stats.count = std::numeric_limits<std::uint64_t>::max();
    EXPECT_THROW(stats.Add(1), std::overflow_error);
}

TEST(CompileInfoSummaryAggregation, FullModeKeepsVectors) {
    const auto full = BuildFullCompileInfo(false);
    EXPECT_FALSE(full.gate_throughput.empty());
    EXPECT_FALSE(full.measurement_feedback_rate.empty());
    EXPECT_FALSE(full.chip_cell_active_qubit_area.empty());
    EXPECT_FALSE(full.gate_throughput_summary.valid);
}

TEST(CompileInfoSummaryAggregation, AggregateKeepsStatsWithoutVectors) {
    const auto summary = BuildAggregateCompileInfo(false);
    EXPECT_TRUE(summary.gate_throughput.empty());
    EXPECT_TRUE(summary.measurement_feedback_rate.empty());
    EXPECT_TRUE(summary.magic_state_consumption_rate.empty());
    EXPECT_TRUE(summary.entanglement_consumption_rate.empty());
    EXPECT_TRUE(summary.chip_cell_algorithmic_qubit.empty());
    EXPECT_TRUE(summary.chip_cell_algorithmic_qubit_ratio.empty());
    EXPECT_TRUE(summary.chip_cell_active_qubit_area.empty());
    EXPECT_TRUE(summary.chip_cell_active_qubit_area_ratio.empty());
    EXPECT_TRUE(summary.gate_throughput_summary.valid);
    EXPECT_TRUE(summary.measurement_feedback_rate_summary.valid);
    EXPECT_TRUE(summary.magic_state_consumption_rate_summary.valid);
    EXPECT_TRUE(summary.entanglement_consumption_rate_summary.valid);
    EXPECT_TRUE(summary.chip_cell_algorithmic_qubit_summary.valid);
    EXPECT_TRUE(summary.chip_cell_algorithmic_qubit_ratio_summary.valid);
    EXPECT_TRUE(summary.chip_cell_active_qubit_area_summary.valid);
    EXPECT_TRUE(summary.chip_cell_active_qubit_area_ratio_summary.valid);
}

TEST(CompileInfoSummaryAggregation, FullAndAggregateGettersMatch) {
    const auto full = BuildFullCompileInfo(false);
    const auto summary = BuildAggregateCompileInfo(false);

    EXPECT_DOUBLE_EQ(summary.GateThroughputAve(), full.GateThroughputAve());
    EXPECT_EQ(summary.GateThroughputPeak(), full.GateThroughputPeak());
    EXPECT_DOUBLE_EQ(summary.MeasurementFeedbackRateAve(), full.MeasurementFeedbackRateAve());
    EXPECT_EQ(summary.MeasurementFeedbackRatePeak(), full.MeasurementFeedbackRatePeak());
    EXPECT_DOUBLE_EQ(
            summary.MagicStateConsumptionRateAve(),
            full.MagicStateConsumptionRateAve()
    );
    EXPECT_EQ(summary.MagicStateConsumptionRatePeak(), full.MagicStateConsumptionRatePeak());
    EXPECT_DOUBLE_EQ(
            summary.EntanglementConsumptionRateAve(),
            full.EntanglementConsumptionRateAve()
    );
    EXPECT_EQ(summary.EntanglementConsumptionRatePeak(), full.EntanglementConsumptionRatePeak());
    EXPECT_DOUBLE_EQ(summary.ChipCellAlgorithmicQubitAve(), full.ChipCellAlgorithmicQubitAve());
    EXPECT_EQ(summary.ChipCellAlgorithmicQubitPeak(), full.ChipCellAlgorithmicQubitPeak());
    EXPECT_DOUBLE_EQ(
            summary.ChipCellAlgorithmicQubitRatioAve(),
            full.ChipCellAlgorithmicQubitRatioAve()
    );
    EXPECT_DOUBLE_EQ(
            summary.ChipCellAlgorithmicQubitRatioPeak(),
            full.ChipCellAlgorithmicQubitRatioPeak()
    );
    EXPECT_DOUBLE_EQ(summary.ChipCellActiveQubitAreaAve(), full.ChipCellActiveQubitAreaAve());
    EXPECT_EQ(summary.ChipCellActiveQubitAreaPeak(), full.ChipCellActiveQubitAreaPeak());
    EXPECT_DOUBLE_EQ(
            summary.ChipCellActiveQubitAreaRatioAve(),
            full.ChipCellActiveQubitAreaRatioAve()
    );
    EXPECT_DOUBLE_EQ(
            summary.ChipCellActiveQubitAreaRatioPeak(),
            full.ChipCellActiveQubitAreaRatioPeak()
    );
    EXPECT_EQ(summary.qubit_volume, full.qubit_volume);
    EXPECT_DOUBLE_EQ(summary.execution_time_sec, full.execution_time_sec);
}

TEST(CompileInfoSummaryAggregation, JsonSchemasAndRawMetricsMatch) {
    const auto full = BuildFullCompileInfo(true);
    const auto summary = BuildAggregateCompileInfo(true);
    const auto full_json = full.Json(CompileInfoOutputMode::Full);
    const auto summary_json = summary.Json(CompileInfoOutputMode::Summary);

    for (const auto* key : TimeSeriesKeys) {
        EXPECT_TRUE(full_json.contains(key)) << key;
        EXPECT_FALSE(summary_json.contains(key)) << key;
        EXPECT_TRUE(summary_json.contains(std::string(key) + "_ave")) << key;
        EXPECT_TRUE(summary_json.contains(std::string(key) + "_peak")) << key;
        EXPECT_EQ(summary_json[std::string(key) + "_ave"], full_json[std::string(key) + "_ave"])
                << key;
        EXPECT_EQ(summary_json[std::string(key) + "_peak"], full_json[std::string(key) + "_peak"])
                << key;
    }

    for (const auto* key : {
                 "runtime",
                 "runtime_without_topology",
                 "gate_count",
                 "gate_count_detail",
                 "gate_depth",
                 "measurement_feedback_count",
                 "measurement_feedback_depth",
                 "magic_state_consumption_count",
                 "magic_state_consumption_depth",
                 "entanglement_consumption_count",
                 "entanglement_consumption_depth",
                 "magic_factory_count",
                 "entanglement_factory_count",
                 "chip_cell_count",
                 "qubit_volume",
                 "code_distance",
                 "execution_time_sec",
                 "num_physical_qubits",
         }) {
        EXPECT_EQ(summary_json[key], full_json[key]) << key;
    }
}

TEST(CompileInfoSummaryAggregation, MarkdownAndStreamValuesMatchWithAndWithoutTopology) {
    for (const auto with_topology : {false, true}) {
        const auto full = BuildFullCompileInfo(with_topology);
        const auto summary = BuildAggregateCompileInfo(with_topology);
        EXPECT_EQ(summary.Markdown(), full.Markdown());

        auto full_stream = std::stringstream();
        auto summary_stream = std::stringstream();
        full_stream << full;
        summary_stream << summary;
        EXPECT_EQ(summary_stream.str(), full_stream.str());
    }
}

TEST(CompileInfoSummaryAggregation, EmptyRuntimeSummaryJsonUsesValidZeroStats) {
    auto summary = ScLsFixedV0CompileInfo();
    summary.gate_throughput_summary.Set(0, 0, 0);
    const auto json = summary.Json(CompileInfoOutputMode::Summary);
    EXPECT_DOUBLE_EQ(json["gate_throughput_ave"].get<double>(), 0.0);
    EXPECT_EQ(json["gate_throughput_peak"].get<std::uint64_t>(), 0);
}

TEST(CompileInfoSummaryAggregation, InvalidSummaryImplementationModeThrows) {
    EXPECT_EQ(
            SummaryTimeSeriesImplementationFromString("vector"),
            SummaryTimeSeriesImplementation::Vector
    );
    EXPECT_EQ(
            SummaryTimeSeriesImplementationFromString("aggregate"),
            SummaryTimeSeriesImplementation::Aggregate
    );
    EXPECT_THROW(SummaryTimeSeriesImplementationFromString("compact"), std::invalid_argument);
}
}  // namespace qret::sc_ls_fixed_v0
