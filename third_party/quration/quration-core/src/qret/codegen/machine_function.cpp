/**
 * @file qret/codegen/machine_function.cpp
 * @brief Machine function.
 */

#include "qret/codegen/machine_function.h"

#include <memory>
#include <utility>

#include "qret/codegen/inverse_map_profile.h"

namespace qret {
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
