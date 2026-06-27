#include "qret/target/sc_ls_fixed_v0/memory_profile_stats.h"

#include <gtest/gtest.h>

#include <fmt/format.h>

#include <sys/types.h>
#include <unistd.h>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "qret/base/json.h"
#include "qret/base/rss_profile.h"
#include "qret/base/string.h"
#include "qret/codegen/machine_function.h"
#include "qret/target/sc_ls_fixed_v0/inst_queue.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
#include "qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_target_machine.h"
#include "qret/target/sc_ls_fixed_v0/simulator.h"
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

std::filesystem::path TempJsonlPath(std::string_view name) {
    return std::filesystem::temp_directory_path()
            / fmt::format("qret_memory_profile_stats_{}_{}.jsonl", getpid(), name);
}

std::vector<qret::Json> LoadJsonl(const std::filesystem::path& path) {
    auto rows = std::vector<qret::Json>();
    auto in = std::ifstream(path);
    auto line = std::string();
    while (std::getline(in, line)) {
        if (!line.empty()) {
            rows.emplace_back(qret::Json::parse(line));
        }
    }
    return rows;
}

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

MachineFunction BuildSmallMachine() {
    auto mf = MachineFunction(&TestTarget());
    auto& bb = mf.AddBlock();
    bb.EmplaceBack(Allocate::New(QSymbol{0}, Coord3D{1, 1, 0}, 0, {}));
    bb.EmplaceBack(Hadamard::New(QSymbol{0}, {CSymbol{7}}));
    bb.EmplaceBack(LatticeSurgery::New(
            {QSymbol{0}, QSymbol{1}},
            {Pauli::Z(), Pauli::X()},
            {Coord3D{1, 2, 0}, Coord3D{2, 2, 0}},
            CSymbol{9},
            {}
    ));
    return mf;
}
}  // namespace

TEST(MemoryProfileStats, ProfilingDisabledDoesNotWriteAllocatorFields) {
    const auto path = TempJsonlPath("disabled");
    std::filesystem::remove(path);
    const auto profile_env = ScopedEnv("QRET_RSS_PROFILE_JSONL", std::nullopt);

    qret::rss_profile::Mark("disabled_marker");

    EXPECT_FALSE(std::filesystem::exists(path));
}

TEST(MemoryProfileStats, ProfilingEnabledWritesAllocatorFields) {
    const auto path = TempJsonlPath("enabled");
    std::filesystem::remove(path);
    const auto profile_env = ScopedEnv("QRET_RSS_PROFILE_JSONL", path.string());

    qret::rss_profile::Mark("enabled_marker");

    const auto rows = LoadJsonl(path);
    ASSERT_EQ(rows.size(), 1);
    EXPECT_EQ(rows.front()["stage"], "enabled_marker");
    EXPECT_TRUE(rows.front().contains("vmrss_kb"));
    EXPECT_TRUE(rows.front().contains("private_dirty_kb"));
    EXPECT_TRUE(rows.front().contains("mallinfo2_supported"));
    if (rows.front()["mallinfo2_supported"].get<bool>()) {
        EXPECT_TRUE(rows.front().contains("mallinfo2_uordblks"));
        EXPECT_TRUE(rows.front().contains("mallinfo2_fordblks"));
        EXPECT_TRUE(rows.front().contains("mallinfo2_keepcost"));
    }
    std::filesystem::remove(path);
}

TEST(MemoryProfileStats, JsonStatsEmptyObject) {
    const auto stats = JsonDomMemoryStats(qret::Json::object());

    EXPECT_EQ(stats["json_root_type"], "object");
    EXPECT_EQ(stats["json_object_count"], 1);
    EXPECT_EQ(stats["json_array_count"], 0);
    EXPECT_EQ(stats["json_scalar_count"], 0);
    EXPECT_EQ(stats["json_object_entry_count"], 0);
    EXPECT_FALSE(stats["json_estimate_is_exact"].get<bool>());
}

TEST(MemoryProfileStats, JsonStatsNestedArrayAndStrings) {
    const auto payload = qret::Json{
            {"name", "abcd"},
            {"items", qret::Json::array({qret::Json{{"k", "xy"}}, 3, true})},
    };

    const auto stats = JsonDomMemoryStats(payload);

    EXPECT_EQ(stats["json_root_type"], "object");
    EXPECT_EQ(stats["json_object_count"], 2);
    EXPECT_EQ(stats["json_array_count"], 1);
    EXPECT_EQ(stats["json_array_element_count"], 3);
    EXPECT_EQ(stats["json_string_count"], 5);
    EXPECT_EQ(stats["json_string_total_size"], 16);
    EXPECT_GT(stats["json_estimated_dynamic_payload_bytes"].get<std::uint64_t>(), 0);
}

TEST(MemoryProfileStats, MachineFunctionStatsEmptyFunction) {
    auto mf = MachineFunction(&TestTarget());

    const auto stats = MachineFunctionMemoryStats(mf);

    EXPECT_EQ(stats["machine_basic_blocks"], 0);
    EXPECT_EQ(stats["machine_instructions"], 0);
    EXPECT_EQ(stats["machine_raw_string_live_count"], 0);
    EXPECT_EQ(stats["machine_total_bytes_estimated"], 0);
}

TEST(MemoryProfileStats, MachineFunctionStatsMultipleInstructionsAndContainers) {
    auto mf = BuildSmallMachine();
    mf.begin()->ConstructInverseMap();

    const auto stats = MachineFunctionMemoryStats(mf);

    EXPECT_EQ(stats["machine_basic_blocks"], 1);
    EXPECT_EQ(stats["machine_instructions"], 3);
    EXPECT_EQ(stats["machine_instruction_type_count"]["ALLOCATE"], 1);
    EXPECT_EQ(stats["machine_instruction_type_count"]["HADAMARD"], 1);
    EXPECT_EQ(stats["machine_instruction_type_count"]["LATTICE_SURGERY"], 1);
    EXPECT_EQ(stats["machine_qtarget_elements"], 4);
    EXPECT_EQ(stats["machine_condition_elements"], 1);
    EXPECT_EQ(stats["machine_ccreate_elements"], 1);
    EXPECT_EQ(stats["machine_path_coordinate_elements"], 2);
    EXPECT_EQ(stats["machine_destination_coordinate_fields"], 1);
    EXPECT_EQ(stats["machine_metadata_objects"], 3);
    EXPECT_GT(stats["machine_operand_list_node_bytes_estimated"].get<std::uint64_t>(), 0);
    EXPECT_GT(stats["machine_instruction_object_bytes_estimated"].get<std::uint64_t>(), 0);
    EXPECT_GT(stats["machine_total_bytes_estimated"].get<std::uint64_t>(), 0);
}

TEST(MemoryProfileStats, RoutingTemporaryStatsUseRealContainers) {
    auto mf = BuildSmallMachine();
    const auto option = TestOption();
    auto queue = InstQueue(option, mf, InstQueue::WeightAlgorithm::InvDepth);
    queue.Peek(16);
    auto simulator = ScLsSimulator(
            *LoadPlaneTopologyFixture(),
            option,
            6,
            SymbolGenerator::New()
    );

    const auto queue_stats = queue.MemoryProfileStats();
    const auto simulator_stats = simulator.MemoryProfileStats();
    const auto live_stats = RoutingLiveMemoryStats(mf, &queue, &simulator);

    EXPECT_GT(queue_stats["routing_queue_nodes"].get<std::uint64_t>(), 0);
    EXPECT_GT(queue_stats["routing_queue_total_bytes_estimated"].get<std::uint64_t>(), 0);
    EXPECT_GT(simulator_stats["routing_sim_avail_p_size"].get<std::uint64_t>(), 0);
    EXPECT_GT(simulator_stats["routing_state_node_capacity"].get<std::uint64_t>(), 0);
    EXPECT_GT(simulator_stats["routing_sim_total_bytes_estimated"].get<std::uint64_t>(), 0);
    EXPECT_GT(live_stats["routing_live_total_bytes_estimated"].get<std::uint64_t>(), 0);
}

TEST(MemoryProfileStats, DiagnosticTrimDefaultNoneAndInvalidValue) {
    const auto trim_env = ScopedEnv("QRET_RSS_DIAGNOSTIC_TRIM_STAGE", std::nullopt);

    EXPECT_FALSE(qret::rss_profile::DiagnosticTrimRequested("after_json_dom_destroy"));
    EXPECT_FALSE(
            qret::rss_profile::DiagnosticTrimRequested("after_routing_temporary_destroy")
    );

    const auto invalid_env = ScopedEnv("QRET_RSS_DIAGNOSTIC_TRIM_STAGE", "invalid");
    EXPECT_THROW(
            qret::rss_profile::DiagnosticTrimRequested("after_json_dom_destroy"),
            std::invalid_argument
    );
}

TEST(MemoryProfileStats, DiagnosticTrimWritesMarkersOnGlibc) {
    const auto path = TempJsonlPath("trim");
    std::filesystem::remove(path);
    const auto profile_env = ScopedEnv("QRET_RSS_PROFILE_JSONL", path.string());
    const auto trim_env =
            ScopedEnv("QRET_RSS_DIAGNOSTIC_TRIM_STAGE", "after_json_dom_destroy");

#if defined(__GLIBC__)
    qret::rss_profile::MaybeDiagnosticTrim("after_json_dom_destroy");
    const auto rows = LoadJsonl(path);
    ASSERT_GE(rows.size(), 2);
    EXPECT_EQ(rows[0]["stage"], "diagnostic_trim_before_after_json_dom_destroy");
    EXPECT_EQ(rows[1]["stage"], "diagnostic_trim_after_after_json_dom_destroy");
    ASSERT_TRUE(rows[1].contains("extra"));
    EXPECT_TRUE(rows[1]["extra"].contains("malloc_trim_return"));
#else
    EXPECT_THROW(
            qret::rss_profile::MaybeDiagnosticTrim("after_json_dom_destroy"),
            std::runtime_error
    );
    const auto rows = LoadJsonl(path);
    ASSERT_EQ(rows.size(), 1);
    EXPECT_EQ(rows[0]["stage"], "diagnostic_trim_unsupported_after_json_dom_destroy");
#endif

    std::filesystem::remove(path);
}
}  // namespace qret::sc_ls_fixed_v0
