#include "qret/target/sc_ls_fixed_v0/magic_path_profile.h"

#include <gtest/gtest.h>

#include <cstdlib>
#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>

#include "qret/base/string.h"
#include "qret/codegen/machine_function.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
#include "qret/target/sc_ls_fixed_v0/memory_profile_stats.h"
#include "qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_target_machine.h"
#include "qret/target/sc_ls_fixed_v0/symbol.h"
#include "qret/target/sc_ls_fixed_v0/topology.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
class ScopedEnv {
public:
    ScopedEnv(std::string key, std::optional<std::string> value)
        : key_(std::move(key)) {
        if (const auto* raw = std::getenv(key_.c_str()); raw != nullptr) {
            old_value_ = std::string(raw);
        }
        if (value.has_value()) {
            setenv(key_.c_str(), value->c_str(), 1);
        } else {
            unsetenv(key_.c_str());
        }
    }
    ScopedEnv(const ScopedEnv&) = delete;
    ScopedEnv& operator=(const ScopedEnv&) = delete;
    ~ScopedEnv() {
        if (old_value_.has_value()) {
            setenv(key_.c_str(), old_value_->c_str(), 1);
        } else {
            unsetenv(key_.c_str());
        }
    }

private:
    std::string key_;
    std::optional<std::string> old_value_;
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

ScLsFixedV0MachineOption TestOption() {
    return ScLsFixedV0MachineOption{
            .magic_generation_period = 15,
            .maximum_magic_state_stock = 100,
            .entanglement_generation_period = 15,
            .maximum_entangled_state_stock = 100,
            .reaction_time = 1,
    };
}

ScLsFixedV0TargetMachine& TestTarget() {
    static auto target = ScLsFixedV0TargetMachine(LoadPlaneTopologyFixture(), TestOption());
    return target;
}

std::unique_ptr<LatticeSurgeryMagic> Magic(
        std::uint64_t index,
        const std::list<Coord3D>& path,
        const std::list<CSymbol>& condition = {}
) {
    return LatticeSurgeryMagic::New(
            {QSymbol{index}},
            {Pauli::X()},
            path,
            CSymbol{100 + index},
            MSymbol{index},
            condition
    );
}

MachineFunction BuildProfileMachine() {
    auto mf = MachineFunction(&TestTarget());
    auto& bb = mf.AddBlock();
    bb.EmplaceBack(Magic(0, {}, {CSymbol{77}}));
    bb.EmplaceBack(Magic(1, {Coord3D{0, 0, 0}}));
    bb.EmplaceBack(Magic(2, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}, Coord3D{2, 0, 0}}));
    bb.EmplaceBack(Magic(3, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}, Coord3D{2, 0, 0}}));
    bb.EmplaceBack(Magic(4, {Coord3D{2, 0, 0}, Coord3D{1, 0, 0}, Coord3D{0, 0, 0}}));
    bb.EmplaceBack(Magic(
            5,
            {Coord3D{10, 10, 0}, Coord3D{11, 10, 0}, Coord3D{12, 10, 0}}
    ));
    bb.EmplaceBack(Magic(6, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}, Coord3D{1, 1, 0}}));
    bb.EmplaceBack(Magic(7, {Coord3D{0, 0, 0}, Coord3D{0, 0, 0}, Coord3D{0, 1, 0}}));
    bb.EmplaceBack(Cnot::New(
            QSymbol{90},
            QSymbol{91},
            {Coord3D{5, 5, 0}, Coord3D{5, 6, 0}},
            {}
    ));
    return mf;
}
}  // namespace

TEST(MagicPathProfile, EnvDefaultOffAndInvalidRejected) {
    const auto unset = ScopedEnv("QRET_PROFILE_MAGIC_PATHS", std::nullopt);
    EXPECT_FALSE(MagicPathProfilingEnabled());

    const auto zero = ScopedEnv("QRET_PROFILE_MAGIC_PATHS", "0");
    EXPECT_FALSE(MagicPathProfilingEnabled());

    const auto one = ScopedEnv("QRET_PROFILE_MAGIC_PATHS", "1");
    EXPECT_TRUE(MagicPathProfilingEnabled());

    const auto invalid = ScopedEnv("QRET_PROFILE_MAGIC_PATHS", "yes");
    EXPECT_THROW(MagicPathProfilingEnabled(), std::invalid_argument);
}

TEST(MagicPathProfile, SegmentCounterCoversStraightBentAndRepeatedPaths) {
    EXPECT_EQ(MagicPathSegmentCountForTest({}), 0);
    EXPECT_EQ(MagicPathSegmentCountForTest({Coord3D{0, 0, 0}}), 0);
    EXPECT_EQ(
            MagicPathSegmentCountForTest(
                    {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}, Coord3D{2, 0, 0}}
            ),
            1
    );
    EXPECT_EQ(
            MagicPathSegmentCountForTest(
                    {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}, Coord3D{1, 1, 0}}
            ),
            2
    );
    EXPECT_EQ(
            MagicPathSegmentCountForTest(
                    {Coord3D{0, 0, 0}, Coord3D{0, 0, 0}, Coord3D{0, 1, 0}}
            ),
            2
    );
}

TEST(MagicPathProfile, SmallMachineReportsDistributionAndMemoryBreakdown) {
    const auto storage_env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "legacy_list");
    auto mf = BuildProfileMachine();
    const auto profile = LatticeSurgeryMagicPathMemoryProfile(mf);

    EXPECT_EQ(profile["profile_schema"], "qret_lattice_surgery_magic_path_memory_v1");
    EXPECT_EQ(profile["path_count"], 8);
    EXPECT_EQ(profile["total_coordinate_count"], 19);
    EXPECT_EQ(profile["length_buckets"]["empty"], 1);
    EXPECT_EQ(profile["length_buckets"]["length_1"], 1);
    EXPECT_EQ(profile["length_buckets"]["length_3"], 6);
    EXPECT_EQ(profile["length_min"], 0);
    EXPECT_EQ(profile["length_max"], 3);
    EXPECT_DOUBLE_EQ(profile["length_median"].get<double>(), 3.0);

    EXPECT_EQ(profile["coordinates"]["x"]["min"], 0);
    EXPECT_EQ(profile["coordinates"]["x"]["max"], 12);
    EXPECT_EQ(profile["coordinates"]["y"]["max"], 10);
    EXPECT_TRUE(profile["coordinates"]["x"]["fits_int8"].get<bool>());
    EXPECT_EQ(profile["coordinates"]["same_coordinate_consecutive_count"], 1);
    EXPECT_GT(profile["coordinates"]["unit_delta_percent"].get<double>(), 0.0);

    EXPECT_EQ(profile["duplicates_exact"]["unique_count"], 7);
    EXPECT_EQ(profile["duplicates_exact"]["duplicate_count"], 1);
    EXPECT_EQ(profile["duplicates_exact"]["most_frequent_count"], 2);
    EXPECT_EQ(profile["duplicates_reverse_canonical"]["unique_count"], 6);
    EXPECT_EQ(profile["duplicates_reverse_canonical"]["duplicate_count"], 2);
    EXPECT_EQ(profile["duplicates_relative_shape"]["unique_count"], 6);
    EXPECT_EQ(profile["duplicates_relative_shape"]["duplicate_count"], 2);

    EXPECT_EQ(profile["segments"]["total_segment_count"], 8);
    EXPECT_EQ(profile["segments"]["path_count_1_segment_or_less"], 6);
    EXPECT_EQ(profile["segments"]["path_count_2_segments_or_less"], 8);
    EXPECT_EQ(profile["segments"]["max_segment_count"], 2);

    const auto& memory = profile["magic_operand_memory"];
    EXPECT_EQ(memory["instruction_count"], 8);
    EXPECT_EQ(memory["qtarget_elements"], 8);
    EXPECT_EQ(memory["basis_elements"], 8);
    EXPECT_EQ(memory["condition_elements"], 1);
    EXPECT_EQ(memory["ccreate_elements"], 8);
    EXPECT_EQ(memory["mtarget_elements"], 8);
    EXPECT_EQ(memory["path_coordinate_elements"], 19);
    EXPECT_GT(memory["path_list_node_bytes_unaligned_estimated"].get<std::uint64_t>(), 0);
    EXPECT_GT(memory["path_list_node_bytes_aligned_estimated"].get<std::uint64_t>(), 0);
    EXPECT_FALSE(memory["list_node_model"]["standard_layout_exact"].get<bool>());

    const auto& all_path = profile["all_machine_ancilla_path_memory"];
    EXPECT_GT(all_path["lattice_surgery_magic_ancilla_path_bytes"].get<std::uint64_t>(), 0);
    EXPECT_GT(all_path["cnot_ancilla_path_bytes"].get<std::uint64_t>(), 0);
    EXPECT_EQ(
            all_path["by_instruction_type"]["LATTICE_SURGERY_MAGIC"]["coordinate_count"],
            19
    );
    EXPECT_EQ(all_path["by_instruction_type"]["CNOT"]["coordinate_count"], 2);

    const auto legacy = MachineFunctionMemoryStats(mf);
    EXPECT_EQ(
            all_path["by_instruction_type"]["LATTICE_SURGERY_MAGIC"]
                    ["list_node_bytes_unaligned_estimated"],
            legacy["machine_instruction_type_ancilla_path_list_node_bytes_estimated"]
                  ["LATTICE_SURGERY_MAGIC"]
    );
}

TEST(MagicPathProfile, HashCollisionFallbackKeepsDistinctPathsDistinct) {
    const auto paths = std::vector<std::list<Coord3D>>{
            {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}},
            {Coord3D{0, 0, 0}, Coord3D{0, 1, 0}},
            {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}},
    };

    const auto profile = MagicPathProfileForPathsForTest(paths, true);

    EXPECT_TRUE(profile["duplicates_exact"]["hash_collision_fallback_used"].get<bool>());
    EXPECT_EQ(profile["duplicates_exact"]["unique_count"], 2);
    EXPECT_EQ(profile["duplicates_exact"]["duplicate_count"], 1);
    EXPECT_GT(profile["duplicates_exact"]["hash_key_compare_count"].get<std::uint64_t>(), 0);
}

TEST(MagicPathProfile, CandidateEstimatesAreTheoreticalAndBounded) {
    const auto profile = MagicPathProfileForPathsForTest(
            {
                    {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}, Coord3D{2, 0, 0}},
                    {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}, Coord3D{2, 0, 0}},
                    {Coord3D{5, 5, 0}, Coord3D{6, 5, 0}, Coord3D{7, 5, 0}},
            }
    );
    const auto& estimates = profile["representation_estimates"];
    const auto current = estimates["current_list_aligned_bytes"].get<std::uint64_t>();
    ASSERT_GT(current, 0);
    ASSERT_FALSE(estimates["rows"].empty());
    auto saw_vector = false;
    auto saw_segment = false;
    for (const auto& row : estimates["rows"]) {
        const auto name = row["representation"].get<std::string>();
        if (name == "std::vector<Coord3D> capacity==size") {
            saw_vector = true;
            EXPECT_LT(row["estimated_bytes"].get<std::uint64_t>(), current);
            EXPECT_EQ(row["semantic_risk"], "low");
        }
        if (name == "segment representation") {
            saw_segment = true;
            EXPECT_EQ(row["semantic_risk"], "medium");
        }
    }
    EXPECT_TRUE(saw_vector);
    EXPECT_TRUE(saw_segment);
}
}  // namespace qret::sc_ls_fixed_v0
