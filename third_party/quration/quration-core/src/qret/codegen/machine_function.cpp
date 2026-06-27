/**
 * @file qret/codegen/machine_function.cpp
 * @brief Machine function.
 */

#include "qret/codegen/machine_function.h"

#include <memory>
#include <utility>

namespace qret {
void MachineBasicBlock::ConstructInverseMap() {
    mp_.clear();
    for (auto itr = instructions_.begin(); itr != instructions_.end(); ++itr) {
        mp_.emplace(itr->get(), itr);
    }
    inverse_map_valid_ = true;
    inverse_map_released_ = false;
}
void MachineBasicBlock::EnsureInverseMap() const {
    if (inverse_map_valid_) {
        return;
    }
    auto& self = const_cast<MachineBasicBlock&>(*this);
    self.ConstructInverseMap();
}
void MachineBasicBlock::ReleaseInverseMap() {
    std::map<const MachineInstruction*, ConstIterator>{}.swap(mp_);
    inverse_map_valid_ = false;
    inverse_map_released_ = true;
}
bool MachineBasicBlock::Contain(const MachineInstruction* inst) const {
    EnsureInverseMap();
    return mp_.contains(inst);
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
}
void MachineBasicBlock::Erase(MachineInstruction* inst) {
    EnsureInverseMap();
    auto itr = mp_.at(inst);
    instructions_.erase(itr);
    mp_.erase(inst);
}
}  // namespace qret
