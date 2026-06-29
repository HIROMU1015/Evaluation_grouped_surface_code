/**
 * @file qret/codegen/machine_function.cpp
 * @brief Machine function.
 */

#include "qret/codegen/machine_function.h"

#include <algorithm>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>
#include <utility>
#include <vector>

#include "qret/codegen/inverse_map_profile.h"

namespace qret {
namespace {
constexpr auto DefaultInstructionArenaChunkBytes = std::size_t{1024 * 1024};
constexpr auto DefaultInstructionArenaAlignment = alignof(std::max_align_t);
thread_local MachineInstructionArena* ActiveInstructionArena = nullptr;

std::mutex& InstructionArenaRegistryMutex() {
    static auto mutex = std::mutex();
    return mutex;
}

std::vector<MachineInstructionArena*>& InstructionArenaRegistry() {
    static auto registry = std::vector<MachineInstructionArena*>();
    return registry;
}

std::size_t AlignUp(std::size_t value, std::size_t alignment) {
    if (alignment == 0) {
        return value;
    }
    const auto remainder = value % alignment;
    if (remainder == 0) {
        return value;
    }
    return value + alignment - remainder;
}

MachineInstructionArena* FindInstructionArena(const void* ptr) {
    if (ptr == nullptr) {
        return nullptr;
    }
    if (ActiveInstructionArena != nullptr && ActiveInstructionArena->Owns(ptr)) {
        return ActiveInstructionArena;
    }
    const auto lock = std::lock_guard<std::mutex>(InstructionArenaRegistryMutex());
    for (auto* arena : InstructionArenaRegistry()) {
        if (arena != nullptr && arena != ActiveInstructionArena && arena->Owns(ptr)) {
            return arena;
        }
    }
    return nullptr;
}
}  // namespace

std::string MachineInstructionAllocationMode() {
    const auto* raw = std::getenv("QRET_INSTRUCTION_ALLOCATION");
    if (raw == nullptr || std::string(raw).empty()) {
        return "legacy";
    }
    const auto mode = std::string(raw);
    if (mode == "legacy" || mode == "arena") {
        return mode;
    }
    throw std::invalid_argument("QRET_INSTRUCTION_ALLOCATION must be legacy or arena");
}

bool MachineInstructionArenaModeEnabled() {
    return MachineInstructionAllocationMode() == "arena";
}

MachineInstructionArena::~MachineInstructionArena() {
    Release();
}

MachineInstructionArena::MachineInstructionArena(MachineInstructionArena&& other) noexcept {
    chunks_ = std::move(other.chunks_);
    allocation_count_ = other.allocation_count_;
    deallocation_count_ = other.deallocation_count_;
    requested_bytes_ = other.requested_bytes_;
    used_bytes_ = other.used_bytes_;
    if (other.registered_) {
        other.Unregister();
        Register();
    }
    other.allocation_count_ = 0;
    other.deallocation_count_ = 0;
    other.requested_bytes_ = 0;
    other.used_bytes_ = 0;
}

MachineInstructionArena&
MachineInstructionArena::operator=(MachineInstructionArena&& other) noexcept {
    if (this == &other) {
        return *this;
    }
    Release();
    chunks_ = std::move(other.chunks_);
    allocation_count_ = other.allocation_count_;
    deallocation_count_ = other.deallocation_count_;
    requested_bytes_ = other.requested_bytes_;
    used_bytes_ = other.used_bytes_;
    if (other.registered_) {
        other.Unregister();
        Register();
    }
    other.allocation_count_ = 0;
    other.deallocation_count_ = 0;
    other.requested_bytes_ = 0;
    other.used_bytes_ = 0;
    return *this;
}

void MachineInstructionArena::Register() {
    if (registered_) {
        return;
    }
    const auto lock = std::lock_guard<std::mutex>(InstructionArenaRegistryMutex());
    InstructionArenaRegistry().push_back(this);
    registered_ = true;
}

void MachineInstructionArena::Unregister() noexcept {
    if (!registered_) {
        return;
    }
    const auto lock = std::lock_guard<std::mutex>(InstructionArenaRegistryMutex());
    auto& registry = InstructionArenaRegistry();
    registry.erase(std::remove(registry.begin(), registry.end(), this), registry.end());
    registered_ = false;
}

void MachineInstructionArena::Release() noexcept {
    Unregister();
    for (auto& chunk : chunks_) {
        if (chunk.data != nullptr) {
            ::operator delete(chunk.data, std::align_val_t(chunk.alignment));
        }
    }
    chunks_.clear();
}

void* MachineInstructionArena::Allocate(std::size_t size, std::size_t alignment) {
    Register();
    const auto effective_alignment = std::max(alignment, DefaultInstructionArenaAlignment);
    auto allocate_from_chunk = [&](Chunk& chunk) -> void* {
        const auto previous_used = chunk.used;
        const auto aligned = AlignUp(chunk.used, effective_alignment);
        if (aligned + size > chunk.size) {
            return nullptr;
        }
        auto* ret = static_cast<std::byte*>(chunk.data) + aligned;
        chunk.used = aligned + size;
        allocation_count_++;
        requested_bytes_ += size;
        used_bytes_ += size + (aligned - previous_used);
        return ret;
    };
    if (!chunks_.empty()) {
        if (auto* ptr = allocate_from_chunk(chunks_.back()); ptr != nullptr) {
            return ptr;
        }
    }
    const auto chunk_size = std::max(DefaultInstructionArenaChunkBytes, AlignUp(size, effective_alignment));
    auto chunk = Chunk{
            .data = ::operator new(chunk_size, std::align_val_t(effective_alignment)),
            .size = chunk_size,
            .used = 0,
            .alignment = effective_alignment,
    };
    chunks_.push_back(chunk);
    return allocate_from_chunk(chunks_.back());
}

bool MachineInstructionArena::Owns(const void* ptr) const {
    const auto* raw = static_cast<const std::byte*>(ptr);
    for (const auto& chunk : chunks_) {
        const auto* begin = static_cast<const std::byte*>(chunk.data);
        const auto* end = begin + chunk.size;
        if (raw >= begin && raw < end) {
            return true;
        }
    }
    return false;
}

bool MachineInstructionArena::Deallocate(const void* ptr) noexcept {
    if (!Owns(ptr)) {
        return false;
    }
    deallocation_count_++;
    return true;
}

MachineInstructionArenaStats MachineInstructionArena::Stats() const {
    auto reserved = std::uint64_t{0};
    for (const auto& chunk : chunks_) {
        reserved += chunk.size;
    }
    return MachineInstructionArenaStats{
            .enabled = registered_ || !chunks_.empty(),
            .allocation_count = allocation_count_,
            .deallocation_count = deallocation_count_,
            .requested_bytes = requested_bytes_,
            .used_bytes = used_bytes_,
            .reserved_bytes = reserved,
            .chunk_count = static_cast<std::uint64_t>(chunks_.size()),
    };
}

MachineInstructionAllocationScope::MachineInstructionAllocationScope(MachineFunction& mf)
    : previous_(ActiveInstructionArena)
    , enabled_(MachineInstructionArenaModeEnabled()) {
    if (enabled_) {
        ActiveInstructionArena = &mf.InstructionArena();
    }
}

MachineInstructionAllocationScope::~MachineInstructionAllocationScope() {
    if (enabled_) {
        ActiveInstructionArena = previous_;
    }
}

void* MachineInstruction::operator new(std::size_t size) {
    if (ActiveInstructionArena != nullptr) {
        return ActiveInstructionArena->Allocate(size, DefaultInstructionArenaAlignment);
    }
    return ::operator new(size);
}

void* MachineInstruction::operator new(std::size_t size, std::align_val_t alignment) {
    if (ActiveInstructionArena != nullptr) {
        return ActiveInstructionArena->Allocate(size, static_cast<std::size_t>(alignment));
    }
    return ::operator new(size, alignment);
}

void MachineInstruction::operator delete(void* ptr) noexcept {
    if (auto* arena = FindInstructionArena(ptr); arena != nullptr && arena->Deallocate(ptr)) {
        return;
    }
    ::operator delete(ptr);
}

void MachineInstruction::operator delete(void* ptr, std::size_t /*size*/) noexcept {
    MachineInstruction::operator delete(ptr);
}

void MachineInstruction::operator delete(void* ptr, std::align_val_t alignment) noexcept {
    if (auto* arena = FindInstructionArena(ptr); arena != nullptr && arena->Deallocate(ptr)) {
        return;
    }
    ::operator delete(ptr, alignment);
}

void MachineInstruction::operator delete(
        void* ptr,
        std::size_t /*size*/,
        std::align_val_t alignment
) noexcept {
    MachineInstruction::operator delete(ptr, alignment);
}

void MachineBasicBlock::ConstructInverseMap() {
    ConstructInverseMapImpl(false);
}
void MachineBasicBlock::ConstructInverseMapImpl(bool from_ensure) {
    const auto was_valid = inverse_map_valid_;
    const auto was_released = inverse_map_released_;
    const auto entries_before = mp_.size();
    auto next = std::map<const MachineInstruction*, ConstIterator>();
    for (auto itr = instructions_.begin(); itr != instructions_.end(); ++itr) {
        next.emplace(itr->get(), itr);
    }
    mp_.swap(next);
    inverse_map_valid_ = true;
    inverse_map_released_ = false;
    inverse_map_profile::RecordConstruct(
            *this,
            was_valid,
            was_released,
            entries_before,
            mp_.size(),
            from_ensure
    );
}
void MachineBasicBlock::EnsureInverseMap() const {
    inverse_map_profile::RecordEnsure(*this, inverse_map_valid_, inverse_map_released_);
    if (inverse_map_valid_) {
        return;
    }
    const auto was_released = inverse_map_released_;
    auto& self = const_cast<MachineBasicBlock&>(*this);
    self.ConstructInverseMapImpl(true);
    inverse_map_profile::RecordLazyRebuild(*this, was_released, self.InverseMapSize());
}
void MachineBasicBlock::ReleaseInverseMap() {
    const auto was_valid = inverse_map_valid_;
    const auto entries_before = mp_.size();
    std::map<const MachineInstruction*, ConstIterator>{}.swap(mp_);
    inverse_map_valid_ = false;
    inverse_map_released_ = true;
    inverse_map_profile::RecordRelease(*this, was_valid, entries_before);
}
bool MachineBasicBlock::Contain(const MachineInstruction* inst) const {
    EnsureInverseMap();
    const auto hit = mp_.contains(inst);
    inverse_map_profile::RecordContain(*this, hit, mp_.size());
    return hit;
}
void MachineBasicBlock::InsertBefore(
        const MachineInstruction* inst,
        std::unique_ptr<MachineInstruction>&& new_inst
) {
    EnsureInverseMap();
    auto* ptr = new_inst.get();
    auto itr = mp_.at(inst);
    itr = instructions_.insert(itr, std::move(new_inst));
    mp_.emplace(ptr, itr);
    inverse_map_profile::RecordInsertBefore(*this, mp_.size());
}
void MachineBasicBlock::InsertAfter(
        const MachineInstruction* inst,
        std::unique_ptr<MachineInstruction>&& new_inst
) {
    EnsureInverseMap();
    auto* ptr = new_inst.get();
    auto itr = mp_.at(inst);
    ++itr;
    itr = instructions_.insert(itr, std::move(new_inst));
    mp_.emplace(ptr, itr);
    inverse_map_profile::RecordInsertAfter(*this, mp_.size());
}
void MachineBasicBlock::Erase(MachineInstruction* inst) {
    EnsureInverseMap();
    auto itr = mp_.at(inst);
    instructions_.erase(itr);
    mp_.erase(inst);
    inverse_map_profile::RecordErase(*this, mp_.size());
}
}  // namespace qret
