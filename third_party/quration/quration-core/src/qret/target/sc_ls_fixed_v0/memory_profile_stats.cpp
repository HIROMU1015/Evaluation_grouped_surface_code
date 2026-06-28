/**
 * @file qret/target/sc_ls_fixed_v0/memory_profile_stats.cpp
 * @brief Profiling-only estimated memory statistics for SC_LS_FIXED_V0.
 */

#include "qret/target/sc_ls_fixed_v0/memory_profile_stats.h"

#include <fmt/format.h>

#include <algorithm>
#include <cstdint>
#include <list>
#include <map>
#include <memory>
#include <string>
#include <unordered_set>
#include <vector>

#include "qret/target/sc_ls_fixed_v0/compile_info.h"
#include "qret/target/sc_ls_fixed_v0/inst_queue.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
#include "qret/target/sc_ls_fixed_v0/magic_path_storage.h"
#include "qret/target/sc_ls_fixed_v0/simulator.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
struct JsonStats {
    std::uint64_t object_count = 0;
    std::uint64_t array_count = 0;
    std::uint64_t scalar_count = 0;
    std::uint64_t string_count = 0;
    std::uint64_t string_total_size = 0;
    std::uint64_t array_element_count = 0;
    std::uint64_t object_entry_count = 0;
};

void VisitJson(const qret::Json& j, JsonStats& stats) {
    if (j.is_object()) {
        ++stats.object_count;
        stats.object_entry_count += j.size();
        for (const auto& [key, value] : j.items()) {
            ++stats.string_count;
            stats.string_total_size += key.size();
            VisitJson(value, stats);
        }
    } else if (j.is_array()) {
        ++stats.array_count;
        stats.array_element_count += j.size();
        for (const auto& value : j) {
            VisitJson(value, stats);
        }
    } else {
        ++stats.scalar_count;
        if (j.is_string()) {
            ++stats.string_count;
            stats.string_total_size += j.get_ref<const std::string&>().size();
        }
    }
}

std::size_t InstructionSize(ScLsInstructionType type) {
    switch (type) {
        case ScLsInstructionType::ALLOCATE:
            return sizeof(Allocate);
        case ScLsInstructionType::ALLOCATE_MAGIC_FACTORY:
            return sizeof(AllocateMagicFactory);
        case ScLsInstructionType::ALLOCATE_ENTANGLEMENT_FACTORY:
            return sizeof(AllocateEntanglementFactory);
        case ScLsInstructionType::DEALLOCATE:
            return sizeof(DeAllocate);
        case ScLsInstructionType::INIT_ZX:
            return sizeof(InitZX);
        case ScLsInstructionType::MEAS_ZX:
            return sizeof(MeasZX);
        case ScLsInstructionType::MEAS_Y:
            return sizeof(MeasY);
        case ScLsInstructionType::TWIST:
            return sizeof(Twist);
        case ScLsInstructionType::HADAMARD:
            return sizeof(Hadamard);
        case ScLsInstructionType::ROTATE:
            return sizeof(Rotate);
        case ScLsInstructionType::LATTICE_SURGERY:
            return sizeof(LatticeSurgery);
        case ScLsInstructionType::LATTICE_SURGERY_MAGIC:
            return sizeof(LatticeSurgeryMagic);
        case ScLsInstructionType::LATTICE_SURGERY_MULTINODE:
            return sizeof(LatticeSurgeryMultinode);
        case ScLsInstructionType::MOVE:
            return sizeof(Move);
        case ScLsInstructionType::MOVE_MAGIC:
            return sizeof(MoveMagic);
        case ScLsInstructionType::MOVE_ENTANGLEMENT:
            return sizeof(MoveEntanglement);
        case ScLsInstructionType::CNOT:
            return sizeof(Cnot);
        case ScLsInstructionType::CNOT_TRANS:
            return sizeof(CnotTrans);
        case ScLsInstructionType::SWAP_TRANS:
            return sizeof(SwapTrans);
        case ScLsInstructionType::MOVE_TRANS:
            return sizeof(MoveTrans);
        case ScLsInstructionType::XOR:
        case ScLsInstructionType::AND:
        case ScLsInstructionType::OR:
            return sizeof(ClassicalOperation);
        case ScLsInstructionType::PROBABILITY_HINT:
            return sizeof(ProbabilityHint);
        case ScLsInstructionType::AWAIT_CORRECTION:
            return sizeof(AwaitCorrection);
        default:
            return sizeof(ScLsInstructionBase);
    }
}

template <typename T>
std::uint64_t ListBytes(const std::list<T>& values) {
    return values.size() * (sizeof(T) + 2 * sizeof(void*));
}

template <typename T>
std::uint64_t VectorCapacityBytes(const std::vector<T>& values) {
    return values.capacity() * sizeof(T);
}

template <typename T>
std::uint64_t MapNodeBytes(const std::map<ScLsInstructionType, T>& values) {
    return values.size()
            * (sizeof(typename std::map<ScLsInstructionType, T>::value_type)
               + 3 * sizeof(void*));
}

std::uint64_t CompileInfoBytes(const qret::CompileInfo* info) {
    const auto* sc_info = dynamic_cast<const ScLsFixedV0CompileInfo*>(info);
    if (sc_info == nullptr) {
        return info == nullptr ? 0 : sizeof(qret::CompileInfo);
    }
    return sizeof(ScLsFixedV0CompileInfo) + MapNodeBytes(sc_info->gate_count_dict)
            + VectorCapacityBytes(sc_info->gate_throughput)
            + VectorCapacityBytes(sc_info->measurement_feedback_rate)
            + VectorCapacityBytes(sc_info->magic_state_consumption_rate)
            + VectorCapacityBytes(sc_info->entanglement_consumption_rate)
            + VectorCapacityBytes(sc_info->chip_cell_algorithmic_qubit)
            + VectorCapacityBytes(sc_info->chip_cell_algorithmic_qubit_ratio)
            + VectorCapacityBytes(sc_info->chip_cell_active_qubit_area)
            + VectorCapacityBytes(sc_info->chip_cell_active_qubit_area_ratio);
}

struct TypeMemoryStats {
    std::uint64_t count = 0;
    std::uint64_t object_bytes = 0;
    std::uint64_t instruction_list_node_bytes = 0;
    std::uint64_t operand_list_node_bytes = 0;
    std::uint64_t ancilla_path_list_node_bytes = 0;
    std::uint64_t destination_coordinate_bytes = 0;
    std::uint64_t metadata_bytes = 0;
};

qret::Json TypeStatsField(
        const std::map<std::string, TypeMemoryStats>& stats,
        std::uint64_t TypeMemoryStats::*field
) {
    auto ret = qret::Json::object();
    for (const auto& [type, item] : stats) {
        ret[type] = item.*field;
    }
    return ret;
}

qret::Json TypeStatsTotal(const std::map<std::string, TypeMemoryStats>& stats) {
    auto ret = qret::Json::object();
    for (const auto& [type, item] : stats) {
        ret[type] = item.object_bytes + item.instruction_list_node_bytes
                + item.operand_list_node_bytes;
    }
    return ret;
}

void AddPrefixed(qret::Json& dest, std::string_view prefix, const qret::Json& source) {
    for (auto it = source.begin(); it != source.end(); ++it) {
        dest[fmt::format("{}{}", prefix, it.key())] = it.value();
    }
}

std::uint64_t DestinationCoordinateFields(ScLsInstructionType type) {
    switch (type) {
        case ScLsInstructionType::ALLOCATE:
        case ScLsInstructionType::ALLOCATE_MAGIC_FACTORY:
            return 1;
        case ScLsInstructionType::ALLOCATE_ENTANGLEMENT_FACTORY:
            return 2;
        default:
            return 0;
    }
}
}  // namespace

qret::Json JsonDomMemoryStats(const qret::Json& j) {
    auto stats = JsonStats();
    VisitJson(j, stats);
    const auto string_capacity_estimate = stats.string_total_size + stats.string_count;
    const auto dynamic_payload_estimate =
            (stats.object_entry_count * (sizeof(std::string) + sizeof(qret::Json) + 2 * sizeof(void*)))
            + (stats.array_element_count * sizeof(qret::Json)) + string_capacity_estimate;

    auto ret = qret::Json::object();
    ret["json_root_type"] = j.type_name();
    ret["json_root_size"] = j.size();
    ret["json_object_count"] = stats.object_count;
    ret["json_array_count"] = stats.array_count;
    ret["json_scalar_count"] = stats.scalar_count;
    ret["json_string_count"] = stats.string_count;
    ret["json_string_total_size"] = stats.string_total_size;
    ret["json_string_total_capacity_estimated"] = string_capacity_estimate;
    ret["json_array_element_count"] = stats.array_element_count;
    ret["json_object_entry_count"] = stats.object_entry_count;
    ret["json_estimated_dynamic_payload_bytes"] = dynamic_payload_estimate;
    ret["json_estimate_is_exact"] = false;
    return ret;
}

qret::Json MachineFunctionMemoryStats(const qret::MachineFunction& mf) {
    auto instruction_count = std::uint64_t{0};
    auto instruction_object_bytes = std::uint64_t{0};
    auto instruction_list_node_bytes = std::uint64_t{0};
    auto inverse_map_entries = std::uint64_t{0};
    auto inverse_map_valid_blocks = std::uint64_t{0};
    auto inverse_map_released_blocks = std::uint64_t{0};
    auto largest_inverse_map_block_entries = std::uint64_t{0};
    auto qtarget_count = std::uint64_t{0};
    auto condition_count = std::uint64_t{0};
    auto cdepend_count = std::uint64_t{0};
    auto ccreate_count = std::uint64_t{0};
    auto mtarget_count = std::uint64_t{0};
    auto etarget_count = std::uint64_t{0};
    auto ehtarget_count = std::uint64_t{0};
    auto ancilla_count = std::uint64_t{0};
    auto destination_coordinate_fields = std::uint64_t{0};
    auto qtarget_list_bytes = std::uint64_t{0};
    auto condition_list_bytes = std::uint64_t{0};
    auto cdepend_list_bytes = std::uint64_t{0};
    auto ccreate_list_bytes = std::uint64_t{0};
    auto mtarget_list_bytes = std::uint64_t{0};
    auto etarget_list_bytes = std::uint64_t{0};
    auto ehtarget_list_bytes = std::uint64_t{0};
    auto ancilla_path_list_bytes = std::uint64_t{0};
    auto operand_list_bytes = std::uint64_t{0};
    auto destination_coordinate_bytes = std::uint64_t{0};
    auto metadata_bytes = std::uint64_t{0};
    auto predecessor_successor_container_bytes = std::uint64_t{0};
    auto inverse_map_entries_by_basic_block = qret::Json::array();
    auto type_counts = qret::Json::object();
    auto type_stats = std::map<std::string, TypeMemoryStats>();
    auto seen_magic_path_storage = std::unordered_set<const void*>();
    auto magic_path_shared_handle_instructions = std::uint64_t{0};
    auto magic_path_legacy_list_instructions = std::uint64_t{0};
    auto magic_path_unique_storage_count = std::uint64_t{0};
    auto magic_path_unique_logical_coordinate_count = std::uint64_t{0};
    auto magic_path_unique_dynamic_bytes = std::uint64_t{0};

    for (const auto& mbb : mf) {
        const auto block_inverse_map_entries = static_cast<std::uint64_t>(mbb.InverseMapSize());
        inverse_map_entries += block_inverse_map_entries;
        largest_inverse_map_block_entries =
                std::max(largest_inverse_map_block_entries, block_inverse_map_entries);
        inverse_map_entries_by_basic_block.emplace_back(block_inverse_map_entries);
        if (mbb.HasInverseMap()) {
            ++inverse_map_valid_blocks;
        }
        if (mbb.InverseMapReleased()) {
            ++inverse_map_released_blocks;
        }
        const auto block_instruction_list_node_bytes =
                mbb.NumInstructions()
                * (sizeof(std::unique_ptr<qret::MachineInstruction>) + 2 * sizeof(void*));
        instruction_list_node_bytes += block_instruction_list_node_bytes;
        predecessor_successor_container_bytes +=
                (mbb.PredSize() + mbb.SuccSize()) * sizeof(qret::MachineBasicBlock*);
        for (const auto& minst : mbb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            const auto type_name = ToString(inst.Type());
            const auto object_size = InstructionSize(inst.Type());
            const auto destination_count = DestinationCoordinateFields(inst.Type());
            const auto list_node_bytes =
                    sizeof(std::unique_ptr<qret::MachineInstruction>) + 2 * sizeof(void*);
            const auto inst_qtarget_list_bytes = ListBytes(inst.QTarget());
            const auto inst_condition_list_bytes = ListBytes(inst.Condition());
            const auto inst_cdepend_list_bytes = ListBytes(inst.CDepend());
            const auto inst_ccreate_list_bytes = ListBytes(inst.CCreate());
            const auto inst_mtarget_list_bytes = ListBytes(inst.MTarget());
            const auto inst_etarget_list_bytes = ListBytes(inst.ETarget());
            const auto inst_ehtarget_list_bytes = ListBytes(inst.EHTarget());
            auto inst_ancilla_path_list_bytes = ListBytes(inst.Ancilla());
            if (inst.Type() == ScLsInstructionType::LATTICE_SURGERY_MAGIC) {
                const auto& magic = static_cast<const LatticeSurgeryMagic&>(inst);
                if (magic.UsesSharedPathStorage()) {
                    ++magic_path_shared_handle_instructions;
                    const auto* identity = magic.PathStorageIdentity();
                    const auto inserted = seen_magic_path_storage.insert(identity).second;
                    if (inserted) {
                        ++magic_path_unique_storage_count;
                        magic_path_unique_logical_coordinate_count +=
                                static_cast<std::uint64_t>(magic.Path().size());
                        inst_ancilla_path_list_bytes =
                                static_cast<std::uint64_t>(sizeof(MagicPathList))
                                + ListBytes(magic.Path());
                        magic_path_unique_dynamic_bytes += inst_ancilla_path_list_bytes;
                    } else {
                        inst_ancilla_path_list_bytes = 0;
                    }
                } else {
                    ++magic_path_legacy_list_instructions;
                }
            }
            const auto inst_operand_list_bytes = inst_qtarget_list_bytes
                    + inst_condition_list_bytes + inst_cdepend_list_bytes
                    + inst_ccreate_list_bytes + inst_mtarget_list_bytes
                    + inst_etarget_list_bytes + inst_ehtarget_list_bytes
                    + inst_ancilla_path_list_bytes;
            auto& per_type = type_stats[type_name];
            ++instruction_count;
            instruction_object_bytes += object_size;
            destination_coordinate_fields += destination_count;
            destination_coordinate_bytes += destination_count * sizeof(Coord3D);
            type_counts[type_name] = type_counts.value(type_name, std::uint64_t{0}) + 1;
            ++per_type.count;
            per_type.object_bytes += object_size;
            per_type.instruction_list_node_bytes += list_node_bytes;
            per_type.operand_list_node_bytes += inst_operand_list_bytes;
            per_type.ancilla_path_list_node_bytes += inst_ancilla_path_list_bytes;
            per_type.destination_coordinate_bytes += destination_count * sizeof(Coord3D);
            per_type.metadata_bytes += sizeof(ScLsMetadata);

            qtarget_count += inst.QTarget().size();
            condition_count += inst.Condition().size();
            cdepend_count += inst.CDepend().size();
            ccreate_count += inst.CCreate().size();
            mtarget_count += inst.MTarget().size();
            etarget_count += inst.ETarget().size();
            ehtarget_count += inst.EHTarget().size();
            ancilla_count += inst.Ancilla().size();
            qtarget_list_bytes += inst_qtarget_list_bytes;
            condition_list_bytes += inst_condition_list_bytes;
            cdepend_list_bytes += inst_cdepend_list_bytes;
            ccreate_list_bytes += inst_ccreate_list_bytes;
            mtarget_list_bytes += inst_mtarget_list_bytes;
            etarget_list_bytes += inst_etarget_list_bytes;
            ehtarget_list_bytes += inst_ehtarget_list_bytes;
            ancilla_path_list_bytes += inst_ancilla_path_list_bytes;
            operand_list_bytes += inst_operand_list_bytes;
            metadata_bytes += sizeof(ScLsMetadata);
        }
    }

    const auto machine_function_object_bytes = sizeof(qret::MachineFunction);
    const auto basic_block_node_bytes =
            mf.NumBBs() * (sizeof(qret::MachineBasicBlock) + 2 * sizeof(void*));
    using InverseMap = std::map<
            const qret::MachineInstruction*,
            qret::MachineBasicBlock::ConstIterator>;
    const auto inverse_map_key_size = sizeof(const qret::MachineInstruction*);
    const auto inverse_map_mapped_iterator_size =
            sizeof(qret::MachineBasicBlock::ConstIterator);
    const auto inverse_map_node_overhead = 3 * sizeof(void*);
    const auto inverse_map_node_bytes =
            sizeof(typename InverseMap::value_type) + inverse_map_node_overhead;
    const auto inverse_map_bytes =
            inverse_map_entries * static_cast<std::uint64_t>(inverse_map_node_bytes);
    const auto compile_info_bytes = CompileInfoBytes(mf.GetCompileInfo());
    const auto ir_pointer_bytes = mf.HasIR() ? sizeof(const qret::ir::Function*) : 0;
    const auto total = instruction_object_bytes + instruction_list_node_bytes
            + basic_block_node_bytes + inverse_map_bytes + operand_list_bytes
            + predecessor_successor_container_bytes + compile_info_bytes;

    auto ret = qret::Json::object();
    ret["machine_function_object_bytes_estimated"] = machine_function_object_bytes;
    ret["machine_basic_blocks"] = mf.NumBBs();
    ret["machine_instructions"] = instruction_count;
    ret["has_ir"] = mf.HasIR();
    ret["has_compile_info"] = mf.HasCompileInfo();
    ret["machine_instruction_type_count"] = type_counts;
    ret["machine_instruction_type_object_bytes_estimated"] =
            TypeStatsField(type_stats, &TypeMemoryStats::object_bytes);
    ret["machine_instruction_type_instruction_list_node_bytes_estimated"] =
            TypeStatsField(type_stats, &TypeMemoryStats::instruction_list_node_bytes);
    ret["machine_instruction_type_operand_list_node_bytes_estimated"] =
            TypeStatsField(type_stats, &TypeMemoryStats::operand_list_node_bytes);
    ret["machine_instruction_type_ancilla_path_list_node_bytes_estimated"] =
            TypeStatsField(type_stats, &TypeMemoryStats::ancilla_path_list_node_bytes);
    ret["machine_instruction_type_destination_coordinate_bytes_estimated"] =
            TypeStatsField(type_stats, &TypeMemoryStats::destination_coordinate_bytes);
    ret["machine_instruction_type_metadata_bytes_estimated"] =
            TypeStatsField(type_stats, &TypeMemoryStats::metadata_bytes);
    ret["machine_instruction_type_total_bytes_estimated"] = TypeStatsTotal(type_stats);
    ret["machine_instruction_object_bytes_estimated"] = instruction_object_bytes;
    ret["machine_instruction_list_node_bytes_estimated"] = instruction_list_node_bytes;
    ret["machine_basic_block_node_bytes_estimated"] = basic_block_node_bytes;
    ret["machine_inverse_map_entries"] = inverse_map_entries;
    ret["machine_inverse_map_valid_blocks"] = inverse_map_valid_blocks;
    ret["machine_inverse_map_released_blocks"] = inverse_map_released_blocks;
    ret["machine_inverse_map_entries_by_basic_block"] = inverse_map_entries_by_basic_block;
    ret["machine_inverse_map_largest_block_entries"] = largest_inverse_map_block_entries;
    ret["machine_inverse_map_key_size_bytes"] = inverse_map_key_size;
    ret["machine_inverse_map_mapped_iterator_size_bytes"] = inverse_map_mapped_iterator_size;
    ret["machine_inverse_map_node_overhead_estimated_bytes"] = inverse_map_node_overhead;
    ret["machine_inverse_map_node_bytes_estimated"] = inverse_map_node_bytes;
    ret["machine_inverse_map_bytes_estimated"] = inverse_map_bytes;
    ret["machine_qtarget_elements"] = qtarget_count;
    ret["machine_condition_elements"] = condition_count;
    ret["machine_cdepend_elements"] = cdepend_count;
    ret["machine_ccreate_elements"] = ccreate_count;
    ret["machine_mtarget_elements"] = mtarget_count;
    ret["machine_etarget_elements"] = etarget_count;
    ret["machine_ehtarget_elements"] = ehtarget_count;
    ret["machine_ancilla_elements"] = ancilla_count;
    ret["machine_path_coordinate_elements"] = ancilla_count;
    ret["machine_destination_coordinate_fields"] = destination_coordinate_fields;
    ret["machine_qtarget_list_node_bytes_estimated"] = qtarget_list_bytes;
    ret["machine_condition_list_node_bytes_estimated"] = condition_list_bytes;
    ret["machine_cdepend_list_node_bytes_estimated"] = cdepend_list_bytes;
    ret["machine_ccreate_list_node_bytes_estimated"] = ccreate_list_bytes;
    ret["machine_mtarget_list_node_bytes_estimated"] = mtarget_list_bytes;
    ret["machine_etarget_list_node_bytes_estimated"] = etarget_list_bytes;
    ret["machine_ehtarget_list_node_bytes_estimated"] = ehtarget_list_bytes;
    ret["machine_ancilla_path_coordinate_list_node_bytes_estimated"] =
            ancilla_path_list_bytes;
    ret["machine_operand_list_node_bytes_estimated"] = operand_list_bytes;
    ret["machine_path_coordinate_list_node_bytes_estimated"] = ancilla_path_list_bytes;
    ret["machine_path_coordinate_list_node_bytes_included_in_total"] = true;
    ret["machine_destination_coordinate_bytes_estimated"] = destination_coordinate_bytes;
    ret["machine_destination_coordinate_bytes_in_instruction_object"] = true;
    ret["machine_metadata_objects"] = instruction_count;
    ret["machine_metadata_bytes_estimated"] = metadata_bytes;
    ret["machine_metadata_bytes_in_instruction_object"] = true;
    ret["machine_predecessor_successor_container_bytes_estimated"] =
            predecessor_successor_container_bytes;
    ret["machine_compile_info_bytes_estimated"] = compile_info_bytes;
    ret["machine_ir_pointer_bytes_estimated"] = ir_pointer_bytes;
    ret["machine_ir_owned_bytes_estimated"] = 0;
    ret["machine_ir_owned_by_machine_function"] = false;
    ret["machine_raw_string_live_count"] = 0;
    ret["machine_raw_string_live_capacity_bytes"] = 0;
    ret["machine_magic_path_storage_mode"] = ToString(ParseMagicPathStorageMode());
    ret["machine_magic_path_shared_handle_instructions"] = magic_path_shared_handle_instructions;
    ret["machine_magic_path_legacy_list_instructions"] = magic_path_legacy_list_instructions;
    ret["machine_magic_path_unique_storage_count"] = magic_path_unique_storage_count;
    ret["machine_magic_path_unique_logical_coordinate_count"] =
            magic_path_unique_logical_coordinate_count;
    ret["machine_magic_path_unique_dynamic_bytes_estimated"] = magic_path_unique_dynamic_bytes;
    auto interner_stats = CurrentMagicPathInternerStats();
    if (interner_stats.empty() && magic_path_shared_handle_instructions > 0) {
        interner_stats = LastMagicPathInternerStats();
    }
    AddPrefixed(ret, "", interner_stats);
    ret["machine_estimate_is_exact"] = false;
    ret["machine_total_bytes_estimated"] = total;
    return ret;
}

qret::Json RoutingLiveMemoryStats(
        const qret::MachineFunction& mf,
        const InstQueue* queue,
        const ScLsSimulator* simulator
) {
    auto ret = MachineFunctionMemoryStats(mf);
    if (queue != nullptr) {
        AddPrefixed(ret, "", queue->MemoryProfileStats());
    }
    if (simulator != nullptr) {
        AddPrefixed(ret, "", simulator->MemoryProfileStats());
    }
    const auto total = ret.value("machine_total_bytes_estimated", std::uint64_t{0})
            + ret.value("routing_queue_total_bytes_estimated", std::uint64_t{0})
            + ret.value("routing_sim_total_bytes_estimated", std::uint64_t{0});
    ret["routing_live_total_bytes_estimated"] = total;
    return ret;
}
}  // namespace qret::sc_ls_fixed_v0
