#include "qret/codegen/inverse_map_profile.h"

#include <gtest/gtest.h>

#include <cstdlib>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>

#include "qret/codegen/machine_function.h"

namespace qret {
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
        inverse_map_profile::ResetForTest();
    }
    ScopedEnv(const ScopedEnv&) = delete;
    ScopedEnv& operator=(const ScopedEnv&) = delete;
    ~ScopedEnv() {
        if (old_value_.has_value()) {
            setenv(key_.c_str(), old_value_->c_str(), 1);
        } else {
            unsetenv(key_.c_str());
        }
        inverse_map_profile::ResetForTest();
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
}  // namespace

TEST(InverseMapProfile, DisabledDoesNotRecord) {
    const auto env = ScopedEnv("QRET_PROFILE_INVERSE_MAP_USAGE", std::nullopt);
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();
    block.EmplaceBack(Dummy("a"));

    block.ConstructInverseMap();

    EXPECT_FALSE(inverse_map_profile::Enabled());
    EXPECT_TRUE(inverse_map_profile::SnapshotJson().empty());
}

TEST(InverseMapProfile, InvalidEnvThrows) {
    const auto env = ScopedEnv("QRET_PROFILE_INVERSE_MAP_USAGE", "yes");

    EXPECT_THROW(inverse_map_profile::Enabled(), std::invalid_argument);
}

TEST(InverseMapProfile, CountsBlockOperations) {
    const auto env = ScopedEnv("QRET_PROFILE_INVERSE_MAP_USAGE", "1");
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();
    auto first = Dummy("a");
    auto second = Dummy("b");
    auto third = Dummy("c");
    auto missing = Dummy("missing");
    auto* first_ptr = first.get();
    auto* second_ptr = second.get();
    auto* third_ptr = third.get();
    block.EmplaceBack(std::move(first));
    block.EmplaceBack(std::move(second));
    block.EmplaceBack(std::move(third));

    {
        const auto stage = inverse_map_profile::StageScope("unit_construct");
        block.ConstructInverseMap();
    }
    {
        const auto stage = inverse_map_profile::StageScope("unit_mutate");
        EXPECT_TRUE(block.Contain(first_ptr));
        EXPECT_FALSE(block.Contain(missing.get()));
        block.InsertBefore(second_ptr, Dummy("before_b"));
        block.InsertAfter(second_ptr, Dummy("after_b"));
        block.Erase(third_ptr);
    }
    {
        const auto stage = inverse_map_profile::StageScope("unit_release");
        block.ReleaseInverseMap();
    }

    const auto stats = inverse_map_profile::SnapshotJson();
    EXPECT_EQ(stats["schema"], "qret_inverse_map_usage_profile_v1");
    EXPECT_EQ(stats["construct_inverse_map_count"], 1);
    EXPECT_EQ(stats["initial_inserted_entries"], 3);
    EXPECT_EQ(stats["ensure_inverse_map_count"], 5);
    EXPECT_EQ(stats["ensure_valid_count"], 5);
    EXPECT_EQ(stats["contain_count"], 2);
    EXPECT_EQ(stats["contain_hit_count"], 1);
    EXPECT_EQ(stats["contain_miss_count"], 1);
    EXPECT_EQ(stats["insert_before_count"], 1);
    EXPECT_EQ(stats["insert_after_count"], 1);
    EXPECT_EQ(stats["erase_count"], 1);
    EXPECT_EQ(stats["release_count"], 1);
    EXPECT_EQ(stats["final_entries_before_release_total"], 4);
    EXPECT_EQ(stats["current_entries"], 0);
    EXPECT_EQ(stats["max_live_entries"], 5);
    EXPECT_EQ(stats["construct_block_entries"].size(), 1);
    EXPECT_EQ(stats["construct_block_entries"][0], 3);
    EXPECT_EQ(stats["release_block_entries"][0], 4);
    EXPECT_EQ(stats["stage_counters"]["unit_construct"]["construct_count"], 1);
    EXPECT_EQ(stats["stage_counters"]["unit_mutate"]["contain_count"], 2);
    EXPECT_EQ(stats["stage_counters"]["unit_release"]["release_count"], 1);
    EXPECT_GT(stats["map_node_bytes_estimated"].get<std::uint64_t>(), 0);
    EXPECT_GT(stats["vector_const_iterator_size_bytes"].get<std::uint64_t>(), 0);
    EXPECT_EQ(stats["stable_instruction_id_size_bytes"], sizeof(std::uint32_t));
}

TEST(InverseMapProfile, LazyRebuildAfterReleaseIsCounted) {
    const auto env = ScopedEnv("QRET_PROFILE_INVERSE_MAP_USAGE", "1");
    auto mf = MachineFunction();
    auto& block = mf.AddBlock();
    auto inst = Dummy("a");
    auto* ptr = inst.get();
    block.EmplaceBack(std::move(inst));
    block.ConstructInverseMap();
    block.ReleaseInverseMap();

    EXPECT_TRUE(block.Contain(ptr));

    const auto stats = inverse_map_profile::SnapshotJson();
    EXPECT_EQ(stats["construct_inverse_map_count"], 2);
    EXPECT_EQ(stats["construct_after_release_count"], 1);
    EXPECT_EQ(stats["lazy_rebuild_count"], 1);
    EXPECT_EQ(stats["lazy_rebuild_after_release_count"], 1);
    EXPECT_EQ(stats["ensure_rebuild_needed_count"], 1);
    EXPECT_EQ(stats["contain_hit_count"], 1);
    EXPECT_EQ(stats["current_entries"], 1);
}
}  // namespace qret
