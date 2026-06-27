#include "qret/target/sc_ls_fixed_v0/calc_compile_info.h"

#include <gtest/gtest.h>

#include <filesystem>
#include <list>
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

MachineFunction BuildMachine(const std::vector<InstSpec>& specs) {
    auto mf = MachineFunction(&TestTarget());
    auto& bb = mf.AddBlock();
    for (const auto& spec : specs) {
        bb.EmplaceBack(std::make_unique<TestInstruction>(spec));
    }
    return mf;
}

void ExpectChipEqual(const TimeSeries::ChipInfo& lhs, const TimeSeries::ChipInfo& rhs) {
    EXPECT_EQ(lhs.space, rhs.space);
    EXPECT_EQ(lhs.q_symb, rhs.q_symb);
    EXPECT_EQ(lhs.m_symb, rhs.m_symb);
    EXPECT_EQ(lhs.e_symb, rhs.e_symb);
    EXPECT_EQ(lhs.used_ancilla_count, rhs.used_ancilla_count);
    EXPECT_EQ(lhs.ChipCellCount(), rhs.ChipCellCount());
    EXPECT_EQ(lhs.ChipCellAlgorithmicQubit(), rhs.ChipCellAlgorithmicQubit());
    EXPECT_DOUBLE_EQ(lhs.ChipCellAlgorithmicQubitRatio(), rhs.ChipCellAlgorithmicQubitRatio());
    EXPECT_EQ(lhs.ChipCellActiveQubitArea(), rhs.ChipCellActiveQubitArea());
    EXPECT_DOUBLE_EQ(lhs.ChipCellActiveQubitAreaRatio(), rhs.ChipCellActiveQubitAreaRatio());
}

void ExpectBeatMetricsEqual(
        const std::vector<SummaryBeatMetrics>& expected,
        const std::vector<SummaryBeatMetrics>& actual
) {
    ASSERT_EQ(actual.size(), expected.size());
    for (auto beat = std::size_t{0}; beat < expected.size(); ++beat) {
        SCOPED_TRACE(::testing::Message() << "beat " << beat);
        EXPECT_EQ(actual[beat].instructions, expected[beat].instructions);
        EXPECT_EQ(actual[beat].gate_throughput, expected[beat].gate_throughput);
        EXPECT_EQ(
                actual[beat].measurement_feedback_rate,
                expected[beat].measurement_feedback_rate
        );
        EXPECT_EQ(
                actual[beat].magic_state_consumption_rate,
                expected[beat].magic_state_consumption_rate
        );
        EXPECT_EQ(
                actual[beat].entanglement_consumption_rate,
                expected[beat].entanglement_consumption_rate
        );
        ExpectChipEqual(actual[beat].chip_info, expected[beat].chip_info);
    }
}

void ExpectAllVariantsMatchLegacy(const std::vector<InstSpec>& specs) {
    auto mf = BuildMachine(specs);
    const auto legacy = CollectLegacyTimeSeriesBeatMetrics(mf);
    const auto compact = CollectCompactTimeSeriesBeatMetrics(mf);
    const auto event_sweep = CollectEventSweepBeatMetrics(mf);
    ExpectBeatMetricsEqual(legacy, compact);
    ExpectBeatMetricsEqual(legacy, event_sweep);
}
}  // namespace

TEST(CompactTimeSeriesParity, EmptyAndLatencyBoundaries) {
    ExpectAllVariantsMatchLegacy({});
    ExpectAllVariantsMatchLegacy({{.name = "zero", .beat = 0, .latency = 0}});
    ExpectAllVariantsMatchLegacy({{.name = "lat1", .beat = 0, .latency = 1}});
    ExpectAllVariantsMatchLegacy({{.name = "lat3", .beat = 0, .latency = 3}});
    ExpectAllVariantsMatchLegacy({{.name = "sparse-zero", .beat = 9, .latency = 0}});
    ExpectAllVariantsMatchLegacy({{.name = "sparse-lat1", .beat = 9, .latency = 1}});
}

TEST(CompactTimeSeriesParity, OverlapOrderIdleBeatsAndUnsortedMachineOrder) {
    ExpectAllVariantsMatchLegacy({
            {.name = "first-mf-order", .beat = 2, .latency = 3},
            {.name = "second-mf-order", .beat = 1, .latency = 2},
            {.name = "same-beat-third", .beat = 2, .latency = 1},
            {.name = "late-after-idle", .beat = 8, .latency = 1},
    });
}

TEST(CompactTimeSeriesParity, ChipStateFactoriesAncillaAndRatios) {
    ExpectAllVariantsMatchLegacy({
            {.name = "alloc-q",
             .beat = 0,
             .latency = 0,
             .type = ScLsInstructionType::ALLOCATE},
            {.name = "ancilla-a", .beat = 1, .latency = 3, .ancilla_count = 2},
            {.name = "ancilla-b", .beat = 2, .latency = 2, .ancilla_count = 5},
            {.name = "magic-factory",
             .beat = 3,
             .latency = 0,
             .type = ScLsInstructionType::ALLOCATE_MAGIC_FACTORY},
            {.name = "entanglement-factory",
             .beat = 4,
             .latency = 0,
             .type = ScLsInstructionType::ALLOCATE_ENTANGLEMENT_FACTORY},
            {.name = "dealloc-q",
             .beat = 6,
             .latency = 0,
             .type = ScLsInstructionType::DEALLOCATE},
    });
}

TEST(CompactTimeSeriesParity, FeedbackReservedCreateConditionAndStartCorrecting) {
    ExpectAllVariantsMatchLegacy({
            {.name = "reserved-condition", .beat = 0, .latency = 0, .condition = {CSymbol{0}}},
            {.name = "create-c10",
             .beat = 1,
             .latency = 0,
             .start_correcting = 2,
             .ccreate = {CSymbol{10}}},
            {.name = "first-condition-c10",
             .beat = 2,
             .latency = 2,
             .condition = {CSymbol{10}}},
            {.name = "second-condition-c10",
             .beat = 3,
             .latency = 1,
             .condition = {CSymbol{10}}},
            {.name = "same-beat-create",
             .beat = 5,
             .latency = 0,
             .ccreate = {CSymbol{11}}},
            {.name = "same-beat-condition",
             .beat = 5,
             .latency = 0,
             .condition = {CSymbol{11}}},
    });
}

TEST(CompactTimeSeriesParity, MagicEntanglementAndMultiBeatCondition) {
    ExpectAllVariantsMatchLegacy({
            {.name = "create-c12", .beat = 0, .latency = 0, .ccreate = {CSymbol{12}}},
            {.name = "magic", .beat = 1, .latency = 3, .use_magic = true},
            {.name = "entanglement", .beat = 2, .latency = 2, .entanglement_count = 4},
            {.name = "condition-c12", .beat = 2, .latency = 3, .condition = {CSymbol{12}}},
    });
}

TEST(CompactTimeSeriesParity, FeedbackErrorsMatchLegacy) {
    for (const auto& specs : std::vector<std::vector<InstSpec>>{
                 {{.name = "unknown", .beat = 0, .latency = 0, .condition = {CSymbol{999}}}},
                 {{.name = "dup-a", .beat = 0, .latency = 0, .ccreate = {CSymbol{20}}},
                  {.name = "dup-b", .beat = 0, .latency = 0, .ccreate = {CSymbol{20}}}},
                 {{.name = "multi-beat-create",
                   .beat = 0,
                   .latency = 2,
                   .ccreate = {CSymbol{21}}}},
         }) {
        auto mf = BuildMachine(specs);
        EXPECT_THROW(CollectLegacyTimeSeriesBeatMetrics(mf), std::runtime_error);
        EXPECT_THROW(CollectCompactTimeSeriesBeatMetrics(mf), std::runtime_error);
        EXPECT_THROW(CollectEventSweepBeatMetrics(mf), std::runtime_error);
    }
}
}  // namespace qret::sc_ls_fixed_v0
