#include "qret/target/sc_ls_fixed_v0/calc_compile_info.h"

#include <gtest/gtest.h>

#include <filesystem>
#include <list>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "qret/base/json.h"
#include "qret/base/string.h"
#include "qret/codegen/machine_function.h"
#include "qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_target_machine.h"
#include "qret/target/sc_ls_fixed_v0/topology.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
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

ScLsFixedV0TargetMachine& TestTarget() {
    static auto target = ScLsFixedV0TargetMachine(LoadPlaneTopologyFixture(), {});
    return target;
}

template <typename T>
TimeSeriesSummaryStats<T> StatsFromVector(const std::vector<T>& values) {
    auto stats = TimeSeriesSummaryStats<T>();
    for (const auto& value : values) {
        stats.Add(value);
    }
    return stats;
}

struct InstSpec {
    std::string name;
    Beat beat = 0;
    Beat latency = 0;
    Beat start_correcting = 0;
    ScLsInstructionType type = ScLsInstructionType::HADAMARD;
    std::uint64_t ancilla_count = 0;
    bool use_magic = false;
    std::uint64_t entanglement_count = 0;
    std::list<CSymbol> ccreate = {};
    std::list<CSymbol> condition = {};
};

class TestInstruction : public ScLsInstructionBase {
public:
    explicit TestInstruction(InstSpec spec)
        : ScLsInstructionBase(spec.condition)
        , spec_{std::move(spec)} {
        MetadataMut().beat = spec_.beat;
    }

    [[nodiscard]] bool IsValidFormat() const override {
        return true;
    }
    [[nodiscard]] ScLsInstructionType Type() const override {
        return spec_.type;
    }
    [[nodiscard]] Beat Latency() const override {
        return spec_.latency;
    }
    [[nodiscard]] Beat StartCorrecting() const override {
        return spec_.start_correcting;
    }
    [[nodiscard]] std::string ToString() const override {
        return spec_.name;
    }
    [[nodiscard]] Json ToJson() const override {
        auto j = DefaultJson();
        j["test_name"] = spec_.name;
        return j;
    }
    [[nodiscard]] const std::list<CSymbol>& CCreate() const override {
        return spec_.ccreate;
    }
    [[nodiscard]] std::size_t CountAncillae() const override {
        return spec_.ancilla_count;
    }
    [[nodiscard]] bool UseMagicState() const override {
        return spec_.use_magic;
    }
    [[nodiscard]] std::size_t CountEntanglement() const override {
        return spec_.entanglement_count;
    }
    [[nodiscard]] bool UseEntanglement() const override {
        return spec_.entanglement_count != 0;
    }

private:
    InstSpec spec_;
};

MachineFunction BuildMachine() {
    auto mf = MachineFunction(&TestTarget());
    auto& bb = mf.AddBlock();
    for (const auto& spec : std::vector<InstSpec>{
                 {.name = "alloc",
                  .beat = 0,
                  .latency = 0,
                  .type = ScLsInstructionType::ALLOCATE},
                 {.name = "create",
                  .beat = 1,
                  .latency = 0,
                  .start_correcting = 1,
                  .ccreate = {CSymbol{10}}},
                 {.name = "magic", .beat = 1, .latency = 3, .use_magic = true},
                 {.name = "ent",
                  .beat = 2,
                  .latency = 2,
                  .ancilla_count = 3,
                  .entanglement_count = 2},
                 {.name = "condition", .beat = 2, .latency = 2, .condition = {CSymbol{10}}},
                 {.name = "dealloc",
                  .beat = 5,
                  .latency = 0,
                  .type = ScLsInstructionType::DEALLOCATE},
         }) {
        bb.EmplaceBack(std::make_unique<TestInstruction>(spec));
    }
    return mf;
}
}  // namespace

TEST(SummaryEventSweep, ScalarsMatchLegacyBeatMetricsAndVectorsStayEmpty) {
    auto mf = BuildMachine();
    const auto legacy = CollectLegacyTimeSeriesBeatMetrics(mf);
    auto gate = std::vector<std::uint64_t>();
    auto feedback = std::vector<std::uint64_t>();
    auto magic = std::vector<std::uint64_t>();
    auto entanglement = std::vector<std::uint64_t>();
    auto algorithmic = std::vector<std::uint64_t>();
    auto algorithmic_ratio = std::vector<double>();
    auto active_area = std::vector<std::uint64_t>();
    auto active_area_ratio = std::vector<double>();
    for (const auto& beat : legacy) {
        gate.emplace_back(beat.gate_throughput);
        feedback.emplace_back(beat.measurement_feedback_rate);
        magic.emplace_back(beat.magic_state_consumption_rate);
        entanglement.emplace_back(beat.entanglement_consumption_rate);
        algorithmic.emplace_back(beat.chip_info.ChipCellAlgorithmicQubit());
        algorithmic_ratio.emplace_back(beat.chip_info.ChipCellAlgorithmicQubitRatio());
        active_area.emplace_back(beat.chip_info.ChipCellActiveQubitArea());
        active_area_ratio.emplace_back(beat.chip_info.ChipCellActiveQubitAreaRatio());
    }

    const auto summary = CalculateEventSweepSummaryForTest(mf);
    EXPECT_TRUE(summary.gate_throughput.empty());
    EXPECT_TRUE(summary.measurement_feedback_rate.empty());
    EXPECT_TRUE(summary.magic_state_consumption_rate.empty());
    EXPECT_TRUE(summary.entanglement_consumption_rate.empty());
    EXPECT_TRUE(summary.chip_cell_algorithmic_qubit.empty());
    EXPECT_TRUE(summary.chip_cell_algorithmic_qubit_ratio.empty());
    EXPECT_TRUE(summary.chip_cell_active_qubit_area.empty());
    EXPECT_TRUE(summary.chip_cell_active_qubit_area_ratio.empty());

    EXPECT_EQ(summary.runtime, legacy.size());
    EXPECT_TRUE(summary.gate_throughput_summary.valid);
    EXPECT_TRUE(summary.measurement_feedback_rate_summary.valid);
    EXPECT_TRUE(summary.magic_state_consumption_rate_summary.valid);
    EXPECT_TRUE(summary.entanglement_consumption_rate_summary.valid);
    EXPECT_TRUE(summary.chip_cell_algorithmic_qubit_summary.valid);
    EXPECT_TRUE(summary.chip_cell_algorithmic_qubit_ratio_summary.valid);
    EXPECT_TRUE(summary.chip_cell_active_qubit_area_summary.valid);
    EXPECT_TRUE(summary.chip_cell_active_qubit_area_ratio_summary.valid);

    auto expected = ScLsFixedV0CompileInfo();
    expected.gate_throughput = gate;
    expected.measurement_feedback_rate = feedback;
    expected.magic_state_consumption_rate = magic;
    expected.entanglement_consumption_rate = entanglement;
    expected.chip_cell_algorithmic_qubit = algorithmic;
    expected.chip_cell_algorithmic_qubit_ratio = algorithmic_ratio;
    expected.chip_cell_active_qubit_area = active_area;
    expected.chip_cell_active_qubit_area_ratio = active_area_ratio;
    expected.qubit_volume =
            std::accumulate(active_area.begin(), active_area.end(), std::uint64_t{0});

    EXPECT_DOUBLE_EQ(summary.GateThroughputAve(), expected.GateThroughputAve());
    EXPECT_EQ(summary.GateThroughputPeak(), expected.GateThroughputPeak());
    EXPECT_DOUBLE_EQ(summary.MeasurementFeedbackRateAve(), expected.MeasurementFeedbackRateAve());
    EXPECT_EQ(summary.MeasurementFeedbackRatePeak(), expected.MeasurementFeedbackRatePeak());
    EXPECT_DOUBLE_EQ(
            summary.MagicStateConsumptionRateAve(),
            expected.MagicStateConsumptionRateAve()
    );
    EXPECT_EQ(summary.MagicStateConsumptionRatePeak(), expected.MagicStateConsumptionRatePeak());
    EXPECT_DOUBLE_EQ(
            summary.EntanglementConsumptionRateAve(),
            expected.EntanglementConsumptionRateAve()
    );
    EXPECT_EQ(
            summary.EntanglementConsumptionRatePeak(),
            expected.EntanglementConsumptionRatePeak()
    );
    EXPECT_DOUBLE_EQ(summary.ChipCellAlgorithmicQubitAve(), expected.ChipCellAlgorithmicQubitAve());
    EXPECT_EQ(summary.ChipCellAlgorithmicQubitPeak(), expected.ChipCellAlgorithmicQubitPeak());
    EXPECT_DOUBLE_EQ(
            summary.ChipCellAlgorithmicQubitRatioAve(),
            expected.ChipCellAlgorithmicQubitRatioAve()
    );
    EXPECT_DOUBLE_EQ(
            summary.ChipCellAlgorithmicQubitRatioPeak(),
            expected.ChipCellAlgorithmicQubitRatioPeak()
    );
    EXPECT_DOUBLE_EQ(summary.ChipCellActiveQubitAreaAve(), expected.ChipCellActiveQubitAreaAve());
    EXPECT_EQ(summary.ChipCellActiveQubitAreaPeak(), expected.ChipCellActiveQubitAreaPeak());
    EXPECT_DOUBLE_EQ(
            summary.ChipCellActiveQubitAreaRatioAve(),
            expected.ChipCellActiveQubitAreaRatioAve()
    );
    EXPECT_DOUBLE_EQ(
            summary.ChipCellActiveQubitAreaRatioPeak(),
            expected.ChipCellActiveQubitAreaRatioPeak()
    );
    EXPECT_EQ(summary.qubit_volume, expected.qubit_volume);
}
}  // namespace qret::sc_ls_fixed_v0
