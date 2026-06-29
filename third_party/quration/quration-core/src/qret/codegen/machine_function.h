/**
 * @file qret/codegen/machine_function.h
 * @brief Machine function.
 * @details This file defines classes for target specific machine functions.
 */

#ifndef QRET_CODEGEN_MACHINE_FUNCTION_H
#define QRET_CODEGEN_MACHINE_FUNCTION_H

#include <cstddef>
#include <cstdint>
#include <list>
#include <map>
#include <memory>
#include <new>
#include <string>
#include <utility>
#include <vector>

#include "qret/codegen/compile_info.h"
#include "qret/codegen/inverse_map_profile.h"
#include "qret/ir/function.h"
#include "qret/qret_export.h"

namespace qret {
// Forward declaration
class TargetMachine;
class MachineFunction;

struct QRET_EXPORT MachineInstructionArenaStats {
    bool enabled = false;
    std::uint64_t allocation_count = 0;
    std::uint64_t deallocation_count = 0;
    std::uint64_t requested_bytes = 0;
    std::uint64_t used_bytes = 0;
    std::uint64_t reserved_bytes = 0;
    std::uint64_t chunk_count = 0;
};

/**
 * @brief Monotonic storage for machine instruction objects.
 */
class QRET_EXPORT MachineInstructionArena {
public:
    MachineInstructionArena() = default;
    ~MachineInstructionArena();
    MachineInstructionArena(const MachineInstructionArena&) = delete;
    MachineInstructionArena& operator=(const MachineInstructionArena&) = delete;
    MachineInstructionArena(MachineInstructionArena&& other) noexcept;
    MachineInstructionArena& operator=(MachineInstructionArena&& other) noexcept;

    void* Allocate(std::size_t size, std::size_t alignment);
    [[nodiscard]] bool Owns(const void* ptr) const;
    bool Deallocate(const void* ptr) noexcept;
    [[nodiscard]] MachineInstructionArenaStats Stats() const;

private:
    struct Chunk {
        void* data = nullptr;
        std::size_t size = 0;
        std::size_t used = 0;
        std::size_t alignment = 0;
    };

    void Register();
    void Unregister() noexcept;
    void Release() noexcept;

    std::vector<Chunk> chunks_ = {};
    std::uint64_t allocation_count_ = 0;
    std::uint64_t deallocation_count_ = 0;
    std::uint64_t requested_bytes_ = 0;
    std::uint64_t used_bytes_ = 0;
    bool registered_ = false;
};

class QRET_EXPORT MachineInstructionAllocationScope {
public:
    explicit MachineInstructionAllocationScope(MachineFunction& mf);
    MachineInstructionAllocationScope(const MachineInstructionAllocationScope&) = delete;
    MachineInstructionAllocationScope& operator=(const MachineInstructionAllocationScope&) =
            delete;
    ~MachineInstructionAllocationScope();

private:
    MachineInstructionArena* previous_ = nullptr;
    bool enabled_ = false;
};

QRET_EXPORT std::string MachineInstructionAllocationMode();
QRET_EXPORT bool MachineInstructionArenaModeEnabled();

/**
 * @brief Basic representation for all target dependent machine instructions used by the backend.
 */
class QRET_EXPORT MachineInstruction {
public:
    static void* operator new(std::size_t size);
    static void* operator new(std::size_t size, std::align_val_t alignment);
    static void operator delete(void* ptr) noexcept;
    static void operator delete(void* ptr, std::size_t size) noexcept;
    static void operator delete(void* ptr, std::align_val_t alignment) noexcept;
    static void operator delete(
            void* ptr,
            std::size_t size,
            std::align_val_t alignment
    ) noexcept;

    virtual ~MachineInstruction() = default;
    [[nodiscard]] virtual std::string ToString() const = 0;
};
/**
 * @brief Collect the sequence of machine instructions for a basic block.
 */
class QRET_EXPORT MachineBasicBlock {
public:
    friend class MachineFunction;
    using Container = std::list<std::unique_ptr<MachineInstruction>>;
    using Iterator = Container::iterator;
    using ConstIterator = Container::const_iterator;

    MachineBasicBlock(const MachineBasicBlock&) = delete;
    MachineBasicBlock& operator=(const MachineBasicBlock&) = delete;
    MachineBasicBlock(MachineBasicBlock&&) noexcept = default;
    MachineBasicBlock& operator=(MachineBasicBlock&&) = default;

    MachineFunction* Parent() {
        return parent_;
    }
    [[nodiscard]] std::size_t PredSize() const {
        return predecessors_.size();
    }
    [[nodiscard]] std::size_t SuccSize() const {
        return successors_.size();
    }

    /**
     * @brief Build the instruction pointer to list iterator map.
     */
    void ConstructInverseMap();
    void EnsureInverseMap() const;
    void ReleaseInverseMap();
    [[nodiscard]] bool HasInverseMap() const {
        return inverse_map_valid_;
    }
    [[nodiscard]] bool InverseMapReleased() const {
        return inverse_map_released_;
    }
    [[nodiscard]] bool InverseMapNeverBuilt() const {
        return !inverse_map_valid_ && !inverse_map_released_ && mp_.empty();
    }
    [[nodiscard]] bool Contain(const MachineInstruction* inst) const;
    void
    InsertBefore(const MachineInstruction* inst, std::unique_ptr<MachineInstruction>&& new_inst);
    void
    InsertAfter(const MachineInstruction* inst, std::unique_ptr<MachineInstruction>&& new_inst);
    void Erase(MachineInstruction* inst);

    void EmplaceBack(std::unique_ptr<MachineInstruction>&& inst) {
        auto* ptr = inst.get();
        instructions_.emplace_back(std::move(inst));
        if (inverse_map_valid_) {
            auto itr = instructions_.end();
            --itr;
            mp_.emplace(ptr, itr);
        }
    }

    std::size_t NumInstructions() const {
        return instructions_.size();
    }
    std::size_t InverseMapSize() const {
        return mp_.size();
    }

    Iterator begin() {
        return instructions_.begin();
    }  // NOLINT
    Iterator end() {
        return instructions_.end();
    }  // NOLINT
    [[nodiscard]] ConstIterator begin() const {
        return instructions_.begin();
    }  // NOLINT
    [[nodiscard]] ConstIterator end() const {
        return instructions_.end();
    }  // NOLINT
    [[nodiscard]] ConstIterator cbegin() const {
        return instructions_.cbegin();
    }  // NOLINT
    [[nodiscard]] ConstIterator cend() const {
        return instructions_.cend();
    }  // NOLINT

private:
    void ConstructInverseMapImpl(bool from_ensure);

    MachineBasicBlock(
            MachineFunction* parent,
            std::list<std::unique_ptr<MachineInstruction>>&& instructions,
            const std::vector<MachineBasicBlock*>& predecessors,
            const std::vector<MachineBasicBlock*>& successors
    )
        : parent_{parent}
        , instructions_{std::move(instructions)}
        , predecessors_{predecessors}
        , successors_{successors} {}

    MachineFunction* parent_;
    std::list<std::unique_ptr<MachineInstruction>> instructions_;
    mutable std::map<const MachineInstruction*, ConstIterator> mp_;
    mutable bool inverse_map_valid_ = false;
    mutable bool inverse_map_released_ = false;
    std::vector<MachineBasicBlock*> predecessors_;  //!< currently not used field
    std::vector<MachineBasicBlock*> successors_;  //!< currently not used field
};
/**
 * @brief This class contains a list of MachineBasicBlock instances that make up the current
 * compiled function.
 */
class QRET_EXPORT MachineFunction {
public:
    using Container = std::list<MachineBasicBlock>;
    using Iterator = Container::iterator;
    using ConstIterator = Container::const_iterator;

    MachineFunction() = default;
    explicit MachineFunction(const TargetMachine* target)
        : target_{target} {}

    MachineFunction(const MachineFunction&) = delete;
    MachineFunction& operator=(const MachineFunction&) = delete;
    MachineFunction(MachineFunction&&) = default;
    MachineFunction& operator=(MachineFunction&&) = default;

    MachineBasicBlock& AddBlock() {
        blocks_.emplace_back(MachineBasicBlock{this, {}, {}, {}});
        return blocks_.back();
    };
    MachineBasicBlock& InsertBlock(ConstIterator itr) {
        return *blocks_.insert(itr, MachineBasicBlock{this, {}, {}, {}});
    }
    void Erase(ConstIterator itr) {
        blocks_.erase(itr);
    }
    void Clear() {
        blocks_.clear();
    }
    void ReleaseInverseMaps() {
        inverse_map_profile::RecordBlockUniverse(*this);
        for (auto& block : blocks_) {
            block.ReleaseInverseMap();
        }
    }

    void SetTarget(const TargetMachine* target) {
        target_ = target;
    }
    [[nodiscard]] const TargetMachine* GetTarget() const {
        return target_;
    }

    std::size_t NumBBs() const {
        return blocks_.size();
    }

    Iterator begin() {
        return blocks_.begin();
    }  // NOLINT
    Iterator end() {
        return blocks_.end();
    }  // NOLINT
    [[nodiscard]] ConstIterator begin() const {
        return blocks_.begin();
    }  // NOLINT
    [[nodiscard]] ConstIterator end() const {
        return blocks_.end();
    }  // NOLINT
    [[nodiscard]] ConstIterator cbegin() const {
        return blocks_.cbegin();
    }  // NOLINT
    [[nodiscard]] ConstIterator cend() const {
        return blocks_.cend();
    }  // NOLINT

    void SetIR(const ir::Function* ir) {
        ir_ = ir;
    }
    bool HasIR() const {
        return ir_ != nullptr;
    }
    const ir::Function* GetIR() const {
        return ir_;
    }

    void InitializeCompileInfo(std::unique_ptr<CompileInfo>&& compile_info) {
        compile_info_ = std::move(compile_info);
    }
    [[nodiscard]] bool HasCompileInfo() const {
        return static_cast<bool>(compile_info_);
    }
    CompileInfo* GetMutCompileInfo() {
        return compile_info_.get();
    }
    const CompileInfo* GetCompileInfo() const {
        return compile_info_.get();
    }
    [[nodiscard]] MachineInstructionArenaStats GetInstructionArenaStats() const {
        return instruction_arena_.Stats();
    }

private:
    friend class MachineInstructionAllocationScope;

    MachineInstructionArena& InstructionArena() {
        return instruction_arena_;
    }

    MachineInstructionArena instruction_arena_ = {};
    const TargetMachine* target_ = nullptr;
    const ir::Function* ir_ = nullptr;
    std::unique_ptr<CompileInfo> compile_info_ = nullptr;
    std::list<MachineBasicBlock> blocks_ = {};
};
}  // namespace qret

#endif  // QRET_TARGET_MACHINE_FUNCTION_H
