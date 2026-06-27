/**
 * @file qret/target/sc_ls_fixed_v0/memory_profile_stats.cpp
 * @brief Profiling-only estimated memory statistics for SC_LS_FIXED_V0.
 */

#include "qret/target/sc_ls_fixed_v0/memory_profile_stats.h"

#include <fmt/format.h>

#include <algorithm>
#include <cstdint>
#include <list>
#include <memory>
#include <string>

#include "qret/target/sc_ls_fixed_v0/inst_queue.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
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
    auto qtarget_count = std::uint64_t{0};
    auto condition_count = std::uint64_t{0};
    auto cdepend_count = std::uint64_t{0};
    auto ccreate_count = std::uint64_t{0};
    auto mtarget_count = std::uint64_t{0};
    auto etarget_count = std::uint64_t{0};
    auto ehtarget_count = std::uint64_t{0};
    auto ancilla_count = std::uint64_t{0};
    auto destination_coordinate_fields = std::uint64_t{0};
    auto operand_list_bytes = std::uint64_t{0};
    auto destination_coordinate_bytes = std::uint64_t{0};
    auto metadata_bytes = std::uint64_t{0};
    auto type_counts = qret::Json::object();
    auto type_object_bytes = qret::Json::object();

    for (const auto& mbb : mf) {
        inverse_map_entries += mbb.InverseMapSize();
        instruction_list_node_bytes +=
                mbb.NumInstructions() * (sizeof(std::unique_ptr<qret::MachineInstruction>) + 2 * sizeof(void*));
        for (const auto& minst : mbb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            const auto type_name = ToString(inst.Type());
            const auto object_size = InstructionSize(inst.Type());
            const auto destination_count = DestinationCoordinateFields(inst.Type());
            ++instruction_count;
            instruction_object_bytes += object_size;
            destination_coordinate_fields += destination_count;
            destination_coordinate_bytes += destination_count * sizeof(Coord3D);
            type_counts[type_name] = type_counts.value(type_name, std::uint64_t{0}) + 1;
            type_object_bytes[type_name] =
                    type_object_bytes.value(type_name, std::uint64_t{0}) + object_size;

            qtarget_count += inst.QTarget().size();
            condition_count += inst.Condition().size();
            cdepend_count += inst.CDepend().size();
            ccreate_count += inst.CCreate().size();
            mtarget_count += inst.MTarget().size();
            etarget_count += inst.ETarget().size();
            ehtarget_count += inst.EHTarget().size();
            ancilla_count += inst.Ancilla().size();
            operand_list_bytes += ListBytes(inst.QTarget()) + ListBytes(inst.Condition())
                    + ListBytes(inst.CDepend()) + ListBytes(inst.CCreate())
                    + ListBytes(inst.MTarget()) + ListBytes(inst.ETarget())
                    + ListBytes(inst.EHTarget()) + ListBytes(inst.Ancilla());
            metadata_bytes += sizeof(ScLsMetadata);
        }
    }

    const auto basic_block_node_bytes =
            mf.NumBBs() * (sizeof(qret::MachineBasicBlock) + 2 * sizeof(void*));
    const auto inverse_map_bytes =
            inverse_map_entries
            * (sizeof(const qret::MachineInstruction*) + sizeof(void*) + 3 * sizeof(void*));
    const auto path_coordinate_list_node_bytes =
            ancilla_count * (sizeof(Coord3D) + 2 * sizeof(void*));
    const auto total = instruction_object_bytes + instruction_list_node_bytes
            + basic_block_node_bytes + inverse_map_bytes + operand_list_bytes
            + destination_coordinate_bytes + metadata_bytes;

    auto ret = qret::Json::object();
    ret["machine_basic_blocks"] = mf.NumBBs();
    ret["machine_instructions"] = instruction_count;
    ret["has_ir"] = mf.HasIR();
    ret["has_compile_info"] = mf.HasCompileInfo();
    ret["machine_instruction_type_count"] = type_counts;
    ret["machine_instruction_type_object_bytes_estimated"] = type_object_bytes;
    ret["machine_instruction_object_bytes_estimated"] = instruction_object_bytes;
    ret["machine_instruction_list_node_bytes_estimated"] = instruction_list_node_bytes;
    ret["machine_basic_block_node_bytes_estimated"] = basic_block_node_bytes;
    ret["machine_inverse_map_entries"] = inverse_map_entries;
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
    ret["machine_operand_list_node_bytes_estimated"] = operand_list_bytes;
    ret["machine_path_coordinate_list_node_bytes_estimated"] = path_coordinate_list_node_bytes;
    ret["machine_destination_coordinate_bytes_estimated"] = destination_coordinate_bytes;
    ret["machine_metadata_objects"] = instruction_count;
    ret["machine_metadata_bytes_estimated"] = metadata_bytes;
    ret["machine_raw_string_live_count"] = 0;
    ret["machine_raw_string_live_capacity_bytes"] = 0;
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
