#include "qret/target/sc_ls_fixed_v0/magic_path_storage.h"

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

std::unique_ptr<LatticeSurgeryMagic> Magic(std::uint64_t index, const std::list<Coord3D>& path) {
    return LatticeSurgeryMagic::New(
            {QSymbol{index}},
            {Pauli::X()},
            path,
            CSymbol{100 + index},
            MSymbol{index},
            {}
    );
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
}  // namespace

TEST(MagicPathStorage, EnvironmentDefaultAndInvalidValue) {
    const auto unset = ScopedEnv("QRET_MAGIC_PATH_STORAGE", std::nullopt);
    EXPECT_EQ(ParseMagicPathStorageMode(), MagicPathStorageMode::Interned);

    const auto legacy = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "legacy_list");
    EXPECT_EQ(ParseMagicPathStorageMode(), MagicPathStorageMode::LegacyList);

    const auto interned = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "interned");
    EXPECT_EQ(ParseMagicPathStorageMode(), MagicPathStorageMode::Interned);

    const auto invalid = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "unique_vector");
    EXPECT_THROW(ParseMagicPathStorageMode(), std::invalid_argument);
}

TEST(MagicPathStorage, InternsExactDuplicateButNotDifferentOrReversedPath) {
    const auto env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "interned");
    auto interner = MagicPathInterner();
    auto scope = MagicPathInterningScope(interner);
    const auto path = std::list<Coord3D>{Coord3D{0, 0, 0}, Coord3D{1, 0, 0}};
    const auto reversed = std::list<Coord3D>{Coord3D{1, 0, 0}, Coord3D{0, 0, 0}};
    const auto other = std::list<Coord3D>{Coord3D{0, 0, 0}, Coord3D{0, 1, 0}};

    auto first = Magic(0, path);
    auto duplicate = Magic(1, path);
    auto reverse_inst = Magic(2, reversed);
    auto other_inst = Magic(3, other);

    EXPECT_TRUE(first->UsesSharedPathStorage());
    EXPECT_EQ(first->PathStorageIdentity(), duplicate->PathStorageIdentity());
    EXPECT_NE(first->PathStorageIdentity(), reverse_inst->PathStorageIdentity());
    EXPECT_NE(first->PathStorageIdentity(), other_inst->PathStorageIdentity());
    EXPECT_EQ(first->Path(), path);
    EXPECT_EQ(reverse_inst->Path(), reversed);

    const auto stats = CurrentMagicPathInternerStats();
    EXPECT_EQ(stats["magic_path_assignment_count"], 4);
    EXPECT_EQ(stats["magic_path_unique_interned_path_count"], 3);
    EXPECT_EQ(stats["magic_path_intern_hit_count"], 1);
    EXPECT_EQ(stats["magic_path_intern_miss_count"], 3);
}

TEST(MagicPathStorage, HashCollisionFallbackDoesNotMisShare) {
    const auto env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "interned");
    auto interner = MagicPathInterner(true);
    auto scope = MagicPathInterningScope(interner);

    auto first = Magic(0, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}});
    auto second = Magic(1, {Coord3D{0, 0, 0}, Coord3D{0, 1, 0}});
    auto duplicate = Magic(2, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}});

    EXPECT_NE(first->PathStorageIdentity(), second->PathStorageIdentity());
    EXPECT_EQ(first->PathStorageIdentity(), duplicate->PathStorageIdentity());
    const auto stats = CurrentMagicPathInternerStats();
    EXPECT_TRUE(stats["magic_path_interner_hash_collision_fallback_used"].get<bool>());
    EXPECT_EQ(stats["magic_path_interner_hash_collision_distinct_key_count"], 1);
    EXPECT_EQ(stats["magic_path_unique_interned_path_count"], 2);
}

TEST(MagicPathStorage, PathSurvivesInternerScopeAndExpiresWithInstruction) {
    const auto env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "interned");
    auto weak = std::weak_ptr<const MagicPathList>();
    auto inst = std::unique_ptr<LatticeSurgeryMagic>();
    {
        auto interner = MagicPathInterner();
        auto scope = MagicPathInterningScope(interner);
        inst = Magic(0, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}});
        weak = inst->PathHandleForTest();
        EXPECT_FALSE(weak.expired());
    }
    EXPECT_FALSE(weak.expired());
    EXPECT_EQ(inst->Path().size(), 2);
    inst.reset();
    EXPECT_TRUE(weak.expired());
}

TEST(MagicPathStorage, IndependentCompilationsDoNotSharePools) {
    const auto env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "interned");
    const auto path = std::list<Coord3D>{Coord3D{0, 0, 0}, Coord3D{1, 0, 0}};
    auto first_handle = MagicPathHandle();
    auto second_handle = MagicPathHandle();
    {
        auto interner = MagicPathInterner();
        auto scope = MagicPathInterningScope(interner);
        auto inst = Magic(0, path);
        first_handle = inst->PathHandleForTest();
    }
    {
        auto interner = MagicPathInterner();
        auto scope = MagicPathInterningScope(interner);
        auto inst = Magic(1, path);
        second_handle = inst->PathHandleForTest();
    }
    ASSERT_NE(first_handle, nullptr);
    ASSERT_NE(second_handle, nullptr);
    EXPECT_NE(first_handle.get(), second_handle.get());
}

TEST(MagicPathStorage, SetPathReassignsStorageAndMaintainsOrder) {
    const auto env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "interned");
    auto interner = MagicPathInterner();
    auto scope = MagicPathInterningScope(interner);
    auto inst = Magic(0, {Coord3D{0, 0, 0}});
    const auto replacement =
            std::list<Coord3D>{Coord3D{2, 0, 0}, Coord3D{2, 1, 0}, Coord3D{2, 2, 0}};

    inst->SetPath(replacement);

    EXPECT_EQ(inst->Path(), replacement);
    EXPECT_EQ(inst->Path().front(), (Coord3D{2, 0, 0}));
    EXPECT_EQ(inst->Path().back(), (Coord3D{2, 2, 0}));
    const auto stats = CurrentMagicPathInternerStats();
    EXPECT_EQ(stats["magic_path_assignment_count"], 2);
}

TEST(MagicPathStorage, JsonRoundTripPreservesPathWithoutInternerScope) {
    const auto env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "interned");
    const auto path =
            std::list<Coord3D>{Coord3D{0, 0, 0}, Coord3D{1, 0, 0}, Coord3D{1, 1, 0}};
    auto original = Magic(0, path);
    const auto json = original->ToJson();
    auto restored = LatticeSurgeryMagic::FromJson(json);

    EXPECT_EQ(restored->Path(), path);
    EXPECT_EQ(restored->ToJson()["ancilla"], json["ancilla"]);
    EXPECT_FALSE(original->UsesSharedPathStorage());
    EXPECT_FALSE(restored->UsesSharedPathStorage());
}

TEST(MagicPathStorage, LegacyModeRetainsListStorage) {
    const auto env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "legacy_list");
    auto inst = Magic(0, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}});

    EXPECT_FALSE(inst->UsesSharedPathStorage());
    EXPECT_EQ(inst->Path().size(), 2);
}

TEST(MagicPathStorage, MachineFunctionStatsCountsUniqueInternedDynamicBytesOnce) {
    const auto env = ScopedEnv("QRET_MAGIC_PATH_STORAGE", "interned");
    auto mf = MachineFunction(&TestTarget());
    {
        auto interner = MagicPathInterner();
        auto scope = MagicPathInterningScope(interner);
        auto& bb = mf.AddBlock();
        bb.EmplaceBack(Magic(0, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}}));
        bb.EmplaceBack(Magic(1, {Coord3D{0, 0, 0}, Coord3D{1, 0, 0}}));
        bb.EmplaceBack(Magic(2, {Coord3D{0, 0, 0}, Coord3D{0, 1, 0}}));
    }

    const auto stats = MachineFunctionMemoryStats(mf);

    EXPECT_EQ(stats["machine_magic_path_storage_mode"], "interned");
    EXPECT_EQ(stats["machine_magic_path_shared_handle_instructions"], 3);
    EXPECT_EQ(stats["machine_magic_path_unique_storage_count"], 2);
    EXPECT_EQ(stats["magic_path_unique_interned_path_count"], 2);
    EXPECT_LT(
            stats["machine_instruction_type_ancilla_path_list_node_bytes_estimated"]
                 ["LATTICE_SURGERY_MAGIC"]
                    .get<std::uint64_t>(),
            3ULL * 2ULL * (sizeof(Coord3D) + 2ULL * sizeof(void*))
    );
}
}  // namespace qret::sc_ls_fixed_v0
