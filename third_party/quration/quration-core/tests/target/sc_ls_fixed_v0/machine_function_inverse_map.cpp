#include "qret/codegen/machine_function.h"

#include <gtest/gtest.h>

#include <cstdlib>
#include <filesystem>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "qret/codegen/inverse_map_profile.h"
#include "qret/base/string.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
#include "qret/target/sc_ls_fixed_v0/routing.h"
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

class DummyInstruction : public MachineInstruction {
public:
    explicit DummyInstruction(std::string name)
        : name_(std::move(name)) {}

    [[nodiscard]] std::string ToString() const override {
        return name_;
    }

private:
    std::string name_;
};

std::unique_ptr<DummyInstruction> Dummy(std::string name) {
    return std::make_unique<DummyInstruction>(std::move(name));
}

std::vector<std::string> Names(const MachineBasicBlock& block) {
    auto ret = std::vector<std::string>();
    for (const auto& inst : block) {
        ret.emplace_back(inst->ToString());
    }
    return ret;
}

std::size_t CountInstructions(const MachineFunction& mf) {
    auto ret = std::size_t{0};
    for (const auto& block : mf) {
        ret += block.NumInstructions();
    }
    return ret;
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

MachineFunction BuildRoutableMachineFunction(const ScLsFixedV0TargetMachine& target) {
    auto mf = MachineFunction(&target);
    auto& alloc = mf.AddBlock();
    auto& block = mf.AddBlock();
    alloc.EmplaceBack(Allocate::New(QSymbol{0}, Coord3D{1, 1, 3}, 0, {}));
    alloc.EmplaceBack(Allocate::New(QSymbol{1}, Coord3D{4, 3, 3}, 0, {}));
    block.EmplaceBack(Cnot::New(QSymbol{0}, QSymbol{1}, {}, {}));
    return mf;
}
}  // namespace

TEST(MachineFunctionInverseMap, EmptyBlockConstructAndRelease) {
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();

    block.ConstructInverseMap();
    EXPECT_TRUE(block.HasInverseMap());
    EXPECT_FALSE(block.InverseMapReleased());
    EXPECT_EQ(block.InverseMapSize(), 0);

    block.ReleaseInverseMap();
    EXPECT_FALSE(block.HasInverseMap());
    EXPECT_TRUE(block.InverseMapReleased());
    EXPECT_EQ(block.InverseMapSize(), 0);
}

TEST(MachineFunctionInverseMap, ConstructTwiceDoesNotDuplicateEntries) {
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();
    block.EmplaceBack(Dummy("a"));
    block.EmplaceBack(Dummy("b"));

    block.ConstructInverseMap();
    block.ConstructInverseMap();

    EXPECT_TRUE(block.HasInverseMap());
    EXPECT_EQ(block.InverseMapSize(), block.NumInstructions());
}

TEST(MachineFunctionInverseMap, ContainLazilyRebuildsAfterRelease) {
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();
    auto inst = Dummy("a");
    auto* ptr = inst.get();
    block.EmplaceBack(std::move(inst));
    block.ConstructInverseMap();
    block.ReleaseInverseMap();

    EXPECT_FALSE(block.HasInverseMap());
    EXPECT_EQ(block.InverseMapSize(), 0);
    EXPECT_TRUE(block.Contain(ptr));
    EXPECT_TRUE(block.HasInverseMap());
    EXPECT_FALSE(block.InverseMapReleased());
    EXPECT_EQ(block.InverseMapSize(), block.NumInstructions());
}

TEST(MachineFunctionInverseMap, InsertBeforeAfterAndEraseLazilyRebuild) {
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();
    auto a = Dummy("a");
    auto b = Dummy("b");
    auto* a_ptr = a.get();
    auto* b_ptr = b.get();
    block.EmplaceBack(std::move(a));
    block.EmplaceBack(std::move(b));
    block.ConstructInverseMap();

    block.ReleaseInverseMap();
    block.InsertBefore(b_ptr, Dummy("before_b"));
    EXPECT_EQ(Names(block), (std::vector<std::string>{"a", "before_b", "b"}));
    EXPECT_TRUE(block.HasInverseMap());
    EXPECT_EQ(block.InverseMapSize(), block.NumInstructions());

    block.ReleaseInverseMap();
    block.InsertAfter(a_ptr, Dummy("after_a"));
    EXPECT_EQ(Names(block), (std::vector<std::string>{"a", "after_a", "before_b", "b"}));
    EXPECT_TRUE(block.HasInverseMap());
    EXPECT_EQ(block.InverseMapSize(), block.NumInstructions());

    block.ReleaseInverseMap();
    block.Erase(a_ptr);
    EXPECT_EQ(Names(block), (std::vector<std::string>{"after_a", "before_b", "b"}));
    EXPECT_TRUE(block.HasInverseMap());
    EXPECT_EQ(block.InverseMapSize(), block.NumInstructions());
}

TEST(MachineFunctionInverseMap, RepeatedReleaseAndRebuildAcrossBlocks) {
    auto mf = MachineFunction();
    auto& first = mf.AddBlock();
    auto& second = mf.AddBlock();
    auto a = Dummy("a");
    auto c = Dummy("c");
    auto* a_ptr = a.get();
    auto* c_ptr = c.get();
    first.EmplaceBack(std::move(a));
    first.EmplaceBack(Dummy("b"));
    second.EmplaceBack(std::move(c));
    first.ConstructInverseMap();
    second.ConstructInverseMap();

    mf.ReleaseInverseMaps();
    mf.ReleaseInverseMaps();
    EXPECT_FALSE(first.HasInverseMap());
    EXPECT_FALSE(second.HasInverseMap());
    EXPECT_TRUE(first.InverseMapReleased());
    EXPECT_TRUE(second.InverseMapReleased());

    EXPECT_TRUE(first.Contain(a_ptr));
    EXPECT_TRUE(second.Contain(c_ptr));
    EXPECT_EQ(first.InverseMapSize(), first.NumInstructions());
    EXPECT_EQ(second.InverseMapSize(), second.NumInstructions());
}

TEST(MachineFunctionInverseMap, CustomPassStyleMutationAfterRelease) {
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();
    auto anchor = Dummy("anchor");
    auto tail = Dummy("tail");
    auto* anchor_ptr = anchor.get();
    auto* tail_ptr = tail.get();
    block.EmplaceBack(std::move(anchor));
    block.EmplaceBack(std::move(tail));
    block.ConstructInverseMap();
    mf.ReleaseInverseMaps();

    ASSERT_TRUE(block.Contain(anchor_ptr));
    block.InsertBefore(anchor_ptr, Dummy("before_anchor"));
    block.InsertAfter(anchor_ptr, Dummy("after_anchor"));
    block.Erase(tail_ptr);

    EXPECT_EQ(Names(block), (std::vector<std::string>{"before_anchor", "anchor", "after_anchor"}));
    EXPECT_EQ(block.InverseMapSize(), block.NumInstructions());
}

TEST(MachineFunctionInverseMap, RoutingReleasesInverseMapsByDefault) {
    const auto release_env = ScopedEnv("QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING", std::nullopt);
    const auto construction_env = ScopedEnv("QRET_INVERSE_MAP_CONSTRUCTION", "eager");
    auto topology = LoadPlaneTopologyFixture();
    const auto target = ScLsFixedV0TargetMachine(topology, TestOption());
    auto mf = BuildRoutableMachineFunction(target);

    Routing().RunOnMachineFunction(mf);

    EXPECT_GT(CountInstructions(mf), 0);
    for (const auto& mbb : mf) {
        EXPECT_FALSE(mbb.HasInverseMap());
        EXPECT_TRUE(mbb.InverseMapReleased());
        EXPECT_EQ(mbb.InverseMapSize(), 0);
    }
}

TEST(MachineFunctionInverseMap, RoutingEagerModeBuildsInverseMapsWhenReleaseDisabled) {
    const auto release_env = ScopedEnv("QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING", "0");
    const auto construction_env = ScopedEnv("QRET_INVERSE_MAP_CONSTRUCTION", "eager");
    auto topology = LoadPlaneTopologyFixture();
    const auto target = ScLsFixedV0TargetMachine(topology, TestOption());
    auto mf = BuildRoutableMachineFunction(target);

    Routing().RunOnMachineFunction(mf);

    for (const auto& mbb : mf) {
        EXPECT_TRUE(mbb.HasInverseMap());
        EXPECT_FALSE(mbb.InverseMapReleased());
        EXPECT_FALSE(mbb.InverseMapNeverBuilt());
        EXPECT_EQ(mbb.InverseMapSize(), mbb.NumInstructions());
    }
}

TEST(MachineFunctionInverseMap, RoutingDefaultKeepsEagerModeUntilLazyCandidateAccepted) {
    const auto release_env = ScopedEnv("QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING", "0");
    const auto construction_env = ScopedEnv("QRET_INVERSE_MAP_CONSTRUCTION", std::nullopt);
    auto topology = LoadPlaneTopologyFixture();
    const auto target = ScLsFixedV0TargetMachine(topology, TestOption());
    auto mf = BuildRoutableMachineFunction(target);

    Routing().RunOnMachineFunction(mf);

    for (const auto& mbb : mf) {
        EXPECT_TRUE(mbb.HasInverseMap());
        EXPECT_FALSE(mbb.InverseMapReleased());
        EXPECT_FALSE(mbb.InverseMapNeverBuilt());
        EXPECT_EQ(mbb.InverseMapSize(), mbb.NumInstructions());
    }
}

TEST(MachineFunctionInverseMap, RoutingLazyModeLeavesUnusedInverseMapsUnbuilt) {
    const auto release_env = ScopedEnv("QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING", "0");
    const auto construction_env = ScopedEnv("QRET_INVERSE_MAP_CONSTRUCTION", "lazy");
    auto topology = LoadPlaneTopologyFixture();
    const auto target = ScLsFixedV0TargetMachine(topology, TestOption());
    auto mf = BuildRoutableMachineFunction(target);

    Routing().RunOnMachineFunction(mf);

    for (const auto& mbb : mf) {
        EXPECT_FALSE(mbb.HasInverseMap());
        EXPECT_FALSE(mbb.InverseMapReleased());
        EXPECT_TRUE(mbb.InverseMapNeverBuilt());
        EXPECT_EQ(mbb.InverseMapSize(), 0);
    }
}

TEST(MachineFunctionInverseMap, InvalidInverseMapConstructionModeThrows) {
    const auto construction_env = ScopedEnv("QRET_INVERSE_MAP_CONSTRUCTION", "invalid");
    auto topology = LoadPlaneTopologyFixture();
    const auto target = ScLsFixedV0TargetMachine(topology, TestOption());
    auto mf = BuildRoutableMachineFunction(target);

    EXPECT_THROW(Routing().RunOnMachineFunction(mf), std::invalid_argument);
}

TEST(MachineFunctionInverseMap, LazyProfileCountersTrackNeverConstructedBlocks) {
    const auto profile_env = ScopedEnv("QRET_PROFILE_INVERSE_MAP_USAGE", "1");
    qret::inverse_map_profile::ResetForTest();
    auto mf = MachineFunction();
    auto& first = mf.AddBlock();
    auto& second = mf.AddBlock();
    auto& third = mf.AddBlock();
    first.EmplaceBack(Dummy("a"));
    auto inst = Dummy("b");
    auto* ptr = inst.get();
    second.EmplaceBack(std::move(inst));
    third.EmplaceBack(Dummy("c"));
    qret::inverse_map_profile::RecordBlockUniverse(mf);

    EXPECT_TRUE(second.Contain(ptr));

    const auto stats = qret::inverse_map_profile::SnapshotJson();
    EXPECT_EQ(stats["constructed_block_count"], 1);
    EXPECT_EQ(stats["never_constructed_block_count"], 2);
    EXPECT_EQ(stats["lazy_construction_count"], 1);
    EXPECT_EQ(stats["lazy_inserted_entries"], 1);
    EXPECT_EQ(stats["max_live_entries"], 1);
    qret::inverse_map_profile::ResetForTest();
}

TEST(MachineFunctionInverseMap, DirectEmplaceBackMaintainsOrDefersInverseMap) {
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();
    auto first = Dummy("first");
    auto* first_ptr = first.get();
    block.EmplaceBack(std::move(first));
    EXPECT_TRUE(block.InverseMapNeverBuilt());

    auto second = Dummy("second");
    auto* second_ptr = second.get();
    block.EmplaceBack(std::move(second));
    EXPECT_TRUE(block.Contain(second_ptr));
    EXPECT_EQ(block.InverseMapSize(), 2);

    auto third = Dummy("third");
    auto* third_ptr = third.get();
    block.EmplaceBack(std::move(third));
    EXPECT_TRUE(block.Contain(first_ptr));
    EXPECT_TRUE(block.Contain(third_ptr));
    EXPECT_EQ(block.InverseMapSize(), 3);
}
}  // namespace qret::sc_ls_fixed_v0
