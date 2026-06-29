/**
 * @file qret/target/sc_ls_fixed_v0/calc_compile_info.cpp
 * @brief Calculate compile information.
 */

#include "qret/target/sc_ls_fixed_v0/calc_compile_info.h"

#include <fmt/core.h>
#include <fmt/ranges.h>

#include <algorithm>
#include <cstddef>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <numeric>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>

#include "qret/base/cast.h"
#include "qret/base/graph.h"
#include "qret/base/log.h"
#include "qret/base/option.h"
#include "qret/base/rss_profile.h"
#include "qret/codegen/machine_function.h"
#include "qret/target/sc_ls_fixed_v0/compile_info.h"
#include "qret/target/sc_ls_fixed_v0/constants.h"
#include "qret/target/sc_ls_fixed_v0/inst_queue.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
#include "qret/target/sc_ls_fixed_v0/routing.h"
#include "qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_target_machine.h"
#include "qret/target/sc_ls_fixed_v0/state.h"
#include "qret/target/sc_ls_fixed_v0/symbol.h"
#include "qret/target/sc_ls_fixed_v0/validation.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
// Register pass to registry
static auto PassWithoutTopology = RegisterPass<CompileInfoWithoutTopology>(
        "CompileInfoWithoutTopology",
        "sc_ls_fixed_v0::calc_info_without_topology"
);
static auto PassWithTopology = RegisterPass<CompileInfoWithTopology>(
        "CompileInfoWithTopology",
        "sc_ls_fixed_v0::calc_info_with_topology"
);
static auto PassWithQEC = RegisterPass<CompileInfoWithQecResourceEstimation>(
        "CompileInfoWithQECResourceEstimation",
        "sc_ls_fixed_v0::calc_info_with_qec_resource_estimation"
);
static auto PassInit =
        RegisterPass<InitCompileInfo>("InitCompileInfo", "sc_ls_fixed_v0::init_compile_info");
static auto PassDump =
        RegisterPass<DumpCompileInfo>("DumpCompileInfo", "sc_ls_fixed_v0::dump_compile_info");

static Opt<std::string> DumpCompileInfoToJson(
        "sc_ls_fixed_v0_dump_compile_info_to_json",
        "",
        "Dump compile information to json",
        OptionHidden::NotHidden
);
static Opt<std::string> DumpCompileInfoToMarkdown(
        "sc_ls_fixed_v0_dump_compile_info_to_markdown",
        "",
        "Dump compile information to markdown",
        OptionHidden::NotHidden
);
static Opt<std::string> CompileInfoOutputModeOption(
        "sc_ls_fixed_v0_compile_info_output_mode",
        "full",
        "Compile-info JSON output mode: 'full' keeps time-series arrays; "
        "'summary' omits them and keeps scalar plus _ave/_peak fields.",
        OptionHidden::NotHidden
);

SummaryTimeSeriesImplementation ParseSummaryTimeSeriesImplementation() {
    const auto* raw = std::getenv("QRET_SUMMARY_TIME_SERIES_IMPL");
    if (raw == nullptr || std::string(raw).empty()) {
        return SummaryTimeSeriesImplementation::LegacyTimeSeries;
    }
    return SummaryTimeSeriesImplementationFromString(raw);
}

qret::Json CompileInfoModeStats(
        CompileInfoOutputMode output_mode,
        SummaryTimeSeriesImplementation summary_impl
) {
    auto extra = qret::Json::object();
    extra["compile_info_output_mode"] = std::string(ToString(output_mode));
    extra["summary_time_series_impl"] = std::string(ToString(summary_impl));
    extra["summary_aggregate_enabled"] =
            output_mode == CompileInfoOutputMode::Summary
            && summary_impl != SummaryTimeSeriesImplementation::Vector;
    return extra;
}

std::size_t CountMachineInstructions(const MachineFunction& mf) {
    auto ret = std::size_t{0};
    for (const auto& mbb : mf) {
        ret += mbb.NumInstructions();
    }
    return ret;
}

std::size_t CountLogicalQubits(const MachineFunction& mf) {
    auto symbols = std::set<QSymbol>();
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            for (const auto q : inst.QTarget()) {
                symbols.insert(q);
            }
        }
    }
    return symbols.size();
}

template <typename T>
void AddVectorStats(
        qret::Json& parent,
        const std::string& name,
        const std::vector<T>& vec,
        std::size_t& total_size,
        std::size_t& total_capacity,
        std::size_t& total_payload_bytes,
        std::size_t& total_capacity_bytes
) {
    const auto size = vec.size();
    const auto capacity = vec.capacity();
    const auto payload_bytes = size * sizeof(T);
    const auto capacity_bytes = capacity * sizeof(T);
    auto item = qret::Json::object();
    item["size"] = size;
    item["capacity"] = capacity;
    item["sizeof_element_bytes"] = sizeof(T);
    item["payload_bytes"] = payload_bytes;
    item["capacity_bytes"] = capacity_bytes;
    parent[name] = item;

    total_size += size;
    total_capacity += capacity;
    total_payload_bytes += payload_bytes;
    total_capacity_bytes += capacity_bytes;
}

template <typename T>
void AddSummaryStats(
        qret::Json& parent,
        const std::string& name,
        const TimeSeriesSummaryStats<T>& stats,
        std::size_t& valid_count,
        std::size_t& total_count,
        std::size_t& total_bytes
) {
    auto item = qret::Json::object();
    item["valid"] = stats.valid;
    item["count"] = stats.count;
    item["sum"] = stats.sum;
    item["peak"] = stats.peak;
    item["sizeof_stats_bytes"] = sizeof(TimeSeriesSummaryStats<T>);
    parent[name] = item;

    valid_count += stats.valid ? 1 : 0;
    total_count += stats.count;
    total_bytes += sizeof(TimeSeriesSummaryStats<T>);
}

qret::Json CompileInfoStats(const ScLsFixedV0CompileInfo& info) {
    auto extra = qret::Json::object();
    extra["compile_info_object_size_bytes"] = sizeof(ScLsFixedV0CompileInfo);
    extra["topology_present"] = info.topology != nullptr;
    extra["runtime"] = info.runtime;
    extra["runtime_without_topology"] = info.runtime_without_topology;
    extra["gate_count"] = info.gate_count;
    extra["gate_depth"] = info.gate_depth;
    extra["measurement_feedback_count"] = info.measurement_feedback_count;
    extra["measurement_feedback_depth"] = info.measurement_feedback_depth;
    extra["magic_state_consumption_count"] = info.magic_state_consumption_count;
    extra["magic_state_consumption_depth"] = info.magic_state_consumption_depth;
    extra["entanglement_consumption_count"] = info.entanglement_consumption_count;
    extra["entanglement_consumption_depth"] = info.entanglement_consumption_depth;
    extra["magic_factory_count"] = info.magic_factory_count;
    extra["entanglement_factory_count"] = info.entanglement_factory_count;
    extra["chip_cell_count"] = info.chip_cell_count;
    extra["qubit_volume"] = info.qubit_volume;
    extra["gate_count_dict_size"] = info.gate_count_dict.size();
    extra["gate_count_dict_estimated_payload_bytes"] =
            info.gate_count_dict.size()
            * (sizeof(ScLsInstructionType) + sizeof(std::uint64_t));

    auto vectors = qret::Json::object();
    auto total_size = std::size_t{0};
    auto total_capacity = std::size_t{0};
    auto total_payload_bytes = std::size_t{0};
    auto total_capacity_bytes = std::size_t{0};
    AddVectorStats(
            vectors,
            "gate_throughput",
            info.gate_throughput,
            total_size,
            total_capacity,
            total_payload_bytes,
            total_capacity_bytes
    );
    AddVectorStats(
            vectors,
            "measurement_feedback_rate",
            info.measurement_feedback_rate,
            total_size,
            total_capacity,
            total_payload_bytes,
            total_capacity_bytes
    );
    AddVectorStats(
            vectors,
            "magic_state_consumption_rate",
            info.magic_state_consumption_rate,
            total_size,
            total_capacity,
            total_payload_bytes,
            total_capacity_bytes
    );
    AddVectorStats(
            vectors,
            "entanglement_consumption_rate",
            info.entanglement_consumption_rate,
            total_size,
            total_capacity,
            total_payload_bytes,
            total_capacity_bytes
    );
    AddVectorStats(
            vectors,
            "chip_cell_algorithmic_qubit",
            info.chip_cell_algorithmic_qubit,
            total_size,
            total_capacity,
            total_payload_bytes,
            total_capacity_bytes
    );
    AddVectorStats(
            vectors,
            "chip_cell_algorithmic_qubit_ratio",
            info.chip_cell_algorithmic_qubit_ratio,
            total_size,
            total_capacity,
            total_payload_bytes,
            total_capacity_bytes
    );
    AddVectorStats(
            vectors,
            "chip_cell_active_qubit_area",
            info.chip_cell_active_qubit_area,
            total_size,
            total_capacity,
            total_payload_bytes,
            total_capacity_bytes
    );
    AddVectorStats(
            vectors,
            "chip_cell_active_qubit_area_ratio",
            info.chip_cell_active_qubit_area_ratio,
            total_size,
            total_capacity,
            total_payload_bytes,
            total_capacity_bytes
    );
    extra["vectors"] = vectors;
    extra["vector_total_size"] = total_size;
    extra["vector_total_capacity"] = total_capacity;
    extra["vector_total_payload_bytes"] = total_payload_bytes;
    extra["vector_total_capacity_bytes"] = total_capacity_bytes;

    auto summaries = qret::Json::object();
    auto summary_valid_count = std::size_t{0};
    auto summary_total_count = std::size_t{0};
    auto summary_total_bytes = std::size_t{0};
    AddSummaryStats(
            summaries,
            "gate_throughput",
            info.gate_throughput_summary,
            summary_valid_count,
            summary_total_count,
            summary_total_bytes
    );
    AddSummaryStats(
            summaries,
            "measurement_feedback_rate",
            info.measurement_feedback_rate_summary,
            summary_valid_count,
            summary_total_count,
            summary_total_bytes
    );
    AddSummaryStats(
            summaries,
            "magic_state_consumption_rate",
            info.magic_state_consumption_rate_summary,
            summary_valid_count,
            summary_total_count,
            summary_total_bytes
    );
    AddSummaryStats(
            summaries,
            "entanglement_consumption_rate",
            info.entanglement_consumption_rate_summary,
            summary_valid_count,
            summary_total_count,
            summary_total_bytes
    );
    AddSummaryStats(
            summaries,
            "chip_cell_algorithmic_qubit",
            info.chip_cell_algorithmic_qubit_summary,
            summary_valid_count,
            summary_total_count,
            summary_total_bytes
    );
    AddSummaryStats(
            summaries,
            "chip_cell_algorithmic_qubit_ratio",
            info.chip_cell_algorithmic_qubit_ratio_summary,
            summary_valid_count,
            summary_total_count,
            summary_total_bytes
    );
    AddSummaryStats(
            summaries,
            "chip_cell_active_qubit_area",
            info.chip_cell_active_qubit_area_summary,
            summary_valid_count,
            summary_total_count,
            summary_total_bytes
    );
    AddSummaryStats(
            summaries,
            "chip_cell_active_qubit_area_ratio",
            info.chip_cell_active_qubit_area_ratio_summary,
            summary_valid_count,
            summary_total_count,
            summary_total_bytes
    );
    extra["summary_stats"] = summaries;
    extra["summary_stats_valid_count"] = summary_valid_count;
    extra["summary_stats_total_count"] = summary_total_count;
    extra["summary_stats_estimated_bytes"] = summary_total_bytes;
    return extra;
}

qret::Json MachineAndCompileInfoStats(
        const MachineFunction& mf,
        const ScLsFixedV0CompileInfo* info = nullptr
) {
    auto extra = qret::Json::object();
    extra["machine_basic_blocks"] = mf.NumBBs();
    extra["machine_instruction_count"] = CountMachineInstructions(mf);
    extra["logical_qubit_count"] = CountLogicalQubits(mf);
    extra["compile_info_present"] = info != nullptr;
    if (info != nullptr) {
        extra["compile_info"] = CompileInfoStats(*info);
    }
    return extra;
}

void MarkCompileInfoStage(
        std::string_view stage,
        const MachineFunction& mf,
        const ScLsFixedV0CompileInfo* info = nullptr
) {
    if (!qret::rss_profile::Enabled()) {
        return;
    }
    qret::rss_profile::Mark(stage, MachineAndCompileInfoStats(mf, info));
}

void MarkCompileInfoStage(
        std::string_view stage,
        const MachineFunction& mf,
        const ScLsFixedV0CompileInfo* info,
        qret::Json extra
) {
    if (!qret::rss_profile::Enabled()) {
        return;
    }
    auto payload = MachineAndCompileInfoStats(mf, info);
    for (auto it = extra.begin(); it != extra.end(); ++it) {
        payload[it.key()] = it.value();
    }
    qret::rss_profile::Mark(stage, payload);
}

qret::Json DepGraphStats(const DepGraph& graph) {
    return graph.ProfileStats();
}

qret::Json InstQueueStats(const InstQueue& queue) {
    auto extra = qret::Json::object();
    extra["inst_queue_nodes"] = queue.NumInsts();
    extra["inst_queue_runnables"] = queue.NumRunnables();
    extra["inst_queue_reserved"] = queue.NumReserved();
    extra["inst_queue_node_estimated_payload_bytes"] = queue.NumInsts() * sizeof(InstQueue::Node);
    return extra;
}

Beat EffectiveTimeSeriesLatency(const ScLsInstructionBase& inst) {
    return inst.Latency() == 0 ? 1 : inst.Latency();
}

std::uint64_t CalculateTimeSeriesRuntime(const MachineFunction& mf) {
    auto raw_runtime = std::uint64_t{0};
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            raw_runtime = std::max(raw_runtime, inst.Metadata().beat + inst.Latency());
        }
    }
    return raw_runtime + 1;
}

void InitializeChipInfoSpace(
        TimeSeries::ChipInfo& chip_info,
        const ScLsFixedV0TargetMachine& target
) {
    auto space = std::int32_t{0};
    for (const auto& grid : *target.topology) {
        space += grid.GetMaxX() * grid.GetMaxY() * grid.GetZSize();
        for (const auto& plane : grid) {
            space -= plane.NumBanned();
        }
    }
    chip_info.space = static_cast<std::uint32_t>(space);
}

void ApplyInstructionToChipInfo(
        TimeSeries::ChipInfo& chip_info,
        const ScLsInstructionBase& inst
) {
    if (inst.Type() == ScLsInstructionType::ALLOCATE) {
        chip_info.q_symb++;
    } else if (inst.Type() == ScLsInstructionType::ALLOCATE_MAGIC_FACTORY) {
        chip_info.m_symb++;
    } else if (inst.Type() == ScLsInstructionType::ALLOCATE_ENTANGLEMENT_FACTORY) {
        chip_info.e_symb += 2;
    } else if (inst.Type() == ScLsInstructionType::DEALLOCATE) {
        chip_info.q_symb--;
    }
    chip_info.used_ancilla_count += inst.CountAncillae();
}

std::vector<const ScLsInstructionBase*> CollectInstructionPointers(const MachineFunction& mf) {
    auto instructions = std::vector<const ScLsInstructionBase*>();
    instructions.reserve(CountMachineInstructions(mf));
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            instructions.emplace_back(static_cast<const ScLsInstructionBase*>(minst.get()));
        }
    }
    return instructions;
}

template <typename Series>
void AddInstructionSequenceStats(
        qret::Json& extra,
        const Series& time_series,
        std::size_t machine_instruction_count
) {
    auto non_empty_beats = std::size_t{0};
    auto max_active = std::size_t{0};
    for (auto beat = std::uint64_t{0}; beat < time_series.GetRuntime(); ++beat) {
        const auto active = time_series.GetInstructions(beat).size();
        if (active != 0) {
            ++non_empty_beats;
        }
        max_active = std::max(max_active, active);
    }
    const auto pointer_count = time_series.InstructionPointerCount();
    extra["beat2inst_non_empty_beat_count"] = non_empty_beats;
    extra["beat2inst_empty_beat_count"] = time_series.GetRuntime() - non_empty_beats;
    extra["beat2inst_max_active_instructions_per_beat"] = max_active;
    extra["beat2inst_average_active_instructions_per_beat"] =
            time_series.GetRuntime() == 0
                    ? 0.0
                    : static_cast<double>(pointer_count)
                              / static_cast<double>(time_series.GetRuntime());
    extra["beat2inst_sum_effective_instruction_latencies"] = pointer_count;
    extra["beat2inst_pointer_duplication_ratio"] =
            machine_instruction_count == 0
                    ? 0.0
                    : static_cast<double>(pointer_count)
                              / static_cast<double>(machine_instruction_count);
}

qret::Json TimeSeriesStats(
        const TimeSeries& time_series,
        std::size_t machine_instruction_count = 0
) {
    auto extra = qret::Json::object();
    extra["time_series_storage_impl"] = "legacy_timeseries";
    extra["time_series_runtime"] = time_series.GetRuntime();
    extra["beat2inst_bucket_count"] = time_series.InstructionBucketCount();
    extra["beat2inst_bucket_capacity"] = time_series.InstructionBucketCapacity();
    extra["beat2inst_outer_size"] = time_series.InstructionBucketCount();
    extra["beat2inst_outer_capacity"] = time_series.InstructionBucketCapacity();
    extra["beat2inst_inner_vector_sizeof"] = sizeof(std::vector<const ScLsInstructionBase*>);
    extra["beat2inst_bucket_object_bytes"] =
            time_series.InstructionBucketCapacity()
            * sizeof(std::vector<const ScLsInstructionBase*>);
    extra["beat2inst_outer_control_block_capacity_bytes"] =
            extra["beat2inst_bucket_object_bytes"];
    extra["beat2inst_pointer_count"] = time_series.InstructionPointerCount();
    extra["beat2inst_pointer_capacity"] = time_series.InstructionPointerCapacity();
    extra["beat2inst_pointer_payload_bytes"] =
            time_series.InstructionPointerCount() * sizeof(const ScLsInstructionBase*);
    extra["beat2inst_pointer_capacity_bytes"] =
            time_series.InstructionPointerCapacity() * sizeof(const ScLsInstructionBase*);
    extra["beat2chip_count"] = time_series.ChipInfoCount();
    extra["beat2chip_capacity"] = time_series.ChipInfoCapacity();
    extra["beat2chip_size"] = time_series.ChipInfoCount();
    extra["beat2chip_sizeof_element_bytes"] = sizeof(TimeSeries::ChipInfo);
    extra["beat2chip_payload_bytes"] = time_series.ChipInfoCount() * sizeof(TimeSeries::ChipInfo);
    extra["beat2chip_capacity_bytes"] =
            time_series.ChipInfoCapacity() * sizeof(TimeSeries::ChipInfo);
    extra["time_series_estimated_capacity_bytes"] =
            extra["beat2inst_outer_control_block_capacity_bytes"].get<std::size_t>()
            + extra["beat2inst_pointer_capacity_bytes"].get<std::size_t>()
            + extra["beat2chip_capacity_bytes"].get<std::size_t>();
    AddInstructionSequenceStats(extra, time_series, machine_instruction_count);
    return extra;
}

qret::Json TimeSeriesStats(
        const CompactTimeSeries& time_series,
        std::size_t machine_instruction_count = 0
) {
    auto extra = qret::Json::object();
    extra["time_series_storage_impl"] = "compact_timeseries";
    extra["time_series_runtime"] = time_series.GetRuntime();
    extra["beat2inst_bucket_count"] = time_series.InstructionBucketCount();
    extra["beat2inst_bucket_capacity"] = time_series.InstructionBucketCapacity();
    extra["beat2inst_outer_size"] = time_series.InstructionBucketCount();
    extra["beat2inst_outer_capacity"] = time_series.InstructionBucketCapacity();
    extra["beat2inst_inner_vector_sizeof"] = sizeof(std::vector<const ScLsInstructionBase*>);
    extra["beat2inst_bucket_object_bytes"] = 0;
    extra["beat2inst_outer_control_block_capacity_bytes"] = 0;
    extra["beat2inst_offset_count"] = time_series.OffsetCount();
    extra["beat2inst_offset_capacity"] = time_series.OffsetCapacity();
    extra["beat2inst_offset_payload_bytes"] =
            time_series.OffsetCount() * sizeof(std::size_t);
    extra["beat2inst_offset_capacity_bytes"] =
            time_series.OffsetCapacity() * sizeof(std::size_t);
    extra["beat2inst_pointer_count"] = time_series.InstructionPointerCount();
    extra["beat2inst_pointer_capacity"] = time_series.InstructionPointerCapacity();
    extra["beat2inst_pointer_payload_bytes"] =
            time_series.InstructionPointerCount() * sizeof(const ScLsInstructionBase*);
    extra["beat2inst_pointer_capacity_bytes"] =
            time_series.InstructionPointerCapacity() * sizeof(const ScLsInstructionBase*);
    extra["beat2chip_count"] = time_series.ChipInfoCount();
    extra["beat2chip_capacity"] = time_series.ChipInfoCapacity();
    extra["beat2chip_size"] = time_series.ChipInfoCount();
    extra["beat2chip_sizeof_element_bytes"] = sizeof(TimeSeries::ChipInfo);
    extra["beat2chip_payload_bytes"] = time_series.ChipInfoCount() * sizeof(TimeSeries::ChipInfo);
    extra["beat2chip_capacity_bytes"] =
            time_series.ChipInfoCapacity() * sizeof(TimeSeries::ChipInfo);
    extra["time_series_estimated_capacity_bytes"] =
            extra["beat2inst_offset_capacity_bytes"].get<std::size_t>()
            + extra["beat2inst_pointer_capacity_bytes"].get<std::size_t>()
            + extra["beat2chip_capacity_bytes"].get<std::size_t>();
    AddInstructionSequenceStats(extra, time_series, machine_instruction_count);
    return extra;
}

struct JsonValueProfileStats {
    std::size_t node_count = 0;
    std::size_t object_count = 0;
    std::size_t array_count = 0;
    std::size_t object_member_count = 0;
    std::size_t array_element_count = 0;
    std::size_t string_count = 0;
    std::size_t string_bytes = 0;
    std::size_t numeric_count = 0;
    std::size_t boolean_count = 0;
    std::size_t null_count = 0;
};

void AccumulateJsonValueStats(const qret::Json& value, JsonValueProfileStats& stats) {
    ++stats.node_count;
    if (value.is_object()) {
        ++stats.object_count;
        stats.object_member_count += value.size();
        for (const auto& item : value.items()) {
            stats.string_bytes += item.key().size();
            AccumulateJsonValueStats(item.value(), stats);
        }
    } else if (value.is_array()) {
        ++stats.array_count;
        stats.array_element_count += value.size();
        for (const auto& item : value) {
            AccumulateJsonValueStats(item, stats);
        }
    } else if (value.is_string()) {
        ++stats.string_count;
        stats.string_bytes += value.get_ref<const std::string&>().size();
    } else if (value.is_number()) {
        ++stats.numeric_count;
    } else if (value.is_boolean()) {
        ++stats.boolean_count;
    } else if (value.is_null()) {
        ++stats.null_count;
    }
}

qret::Json JsonValueStats(const qret::Json& value) {
    auto stats = JsonValueProfileStats{};
    AccumulateJsonValueStats(value, stats);
    auto extra = qret::Json::object();
    extra["json_node_count"] = stats.node_count;
    extra["json_object_count"] = stats.object_count;
    extra["json_array_count"] = stats.array_count;
    extra["json_object_member_count"] = stats.object_member_count;
    extra["json_array_element_count"] = stats.array_element_count;
    extra["json_string_count"] = stats.string_count;
    extra["json_string_bytes"] = stats.string_bytes;
    extra["json_numeric_count"] = stats.numeric_count;
    extra["json_boolean_count"] = stats.boolean_count;
    extra["json_null_count"] = stats.null_count;
    extra["json_top_level_size"] = value.size();
    return extra;
}
}  // namespace

CompactDepGraph::CompactDepGraph()
    : parent_offsets_{0} {}

CompactDepGraph::IdType CompactDepGraph::AddNode(Weight weight) {
    if (finalized_) {
        throw std::logic_error("Cannot add node after finalizing CompactDepGraph.");
    }
    SealCurrentNodeIfNeeded();
    if (node_weights_.size() >= std::numeric_limits<IdType>::max()) {
        throw std::overflow_error("CompactDepGraph node id overflow.");
    }
    node_weights_.push_back(weight);
    current_node_open_ = true;
    return static_cast<IdType>(node_weights_.size() - 1);
}

void CompactDepGraph::AddEdgeToCurrentNode(IdType from, Length length) {
    if (!current_node_open_ || node_weights_.empty()) {
        throw std::logic_error("CompactDepGraph has no current node.");
    }
    const auto to = static_cast<IdType>(node_weights_.size() - 1);
    if (from >= to) {
        topological_order_invariant_ = false;
        throw std::logic_error("CompactDepGraph requires from_id < to_id.");
    }
    const auto start = static_cast<std::size_t>(parent_offsets_.back());
    const auto end = parent_ids_.size();
    for (auto i = start; i < end; ++i) {
        if (parent_ids_[i] == from) {
            edge_lengths_[i] = length;
            ++duplicate_edge_count_;
            return;
        }
    }
    parent_ids_.push_back(from);
    edge_lengths_.push_back(length);
    max_indegree_ = std::max(max_indegree_, parent_ids_.size() - start);
}

void CompactDepGraph::Finalize() {
    if (finalized_) {
        return;
    }
    SealCurrentNodeIfNeeded();
    finalized_ = true;
    if (parent_offsets_.size() != node_weights_.size() + 1) {
        throw std::logic_error("CompactDepGraph parent offset invariant failed.");
    }
}

void CompactDepGraph::SetNodeWeight(IdType id, Weight weight) {
    CheckNode(id);
    node_weights_[id] = weight;
}

void CompactDepGraph::SetAllLength(Length length) {
    Finalize();
    std::fill(edge_lengths_.begin(), edge_lengths_.end(), length);
}

void CompactDepGraph::SetLength(IdType from, IdType to, Length length) {
    Finalize();
    CheckNode(from);
    CheckNode(to);
    const auto start = parent_offsets_[to];
    const auto end = parent_offsets_[static_cast<std::size_t>(to) + 1];
    for (auto i = start; i < end; ++i) {
        if (parent_ids_[i] == from) {
            edge_lengths_[i] = length;
            return;
        }
    }
    throw std::out_of_range("CompactDepGraph edge is not found.");
}

CompactDepGraph::Weight CompactDepGraph::CalcHeaviest() const {
    CheckFinalized();
    working_dp_.assign(node_weights_.size(), 0);
    auto ret = Weight{0};
    for (auto id = std::size_t{0}; id < node_weights_.size(); ++id) {
        auto parent_max = Weight{0};
        for (auto edge_i = parent_offsets_[id]; edge_i < parent_offsets_[id + 1]; ++edge_i) {
            parent_max = std::max(parent_max, working_dp_[parent_ids_[edge_i]]);
        }
        working_dp_[id] = parent_max + node_weights_[id];
        ret = std::max(ret, working_dp_[id]);
    }
    return ret;
}

CompactDepGraph::Length CompactDepGraph::CalcLongest() const {
    CheckFinalized();
    working_dp_.assign(node_weights_.size(), 0);
    auto ret = Length{0};
    for (auto id = std::size_t{0}; id < node_weights_.size(); ++id) {
        auto parent_max = Length{0};
        for (auto edge_i = parent_offsets_[id]; edge_i < parent_offsets_[id + 1]; ++edge_i) {
            const auto parent = parent_ids_[edge_i];
            parent_max = std::max(parent_max, working_dp_[parent] + edge_lengths_[edge_i]);
        }
        working_dp_[id] = parent_max;
        ret = std::max(ret, working_dp_[id]);
    }
    return ret;
}

std::size_t CompactDepGraph::NumNodes() const {
    return node_weights_.size();
}

std::size_t CompactDepGraph::NumEdges() const {
    return parent_ids_.size();
}

std::size_t CompactDepGraph::DuplicateEdgeCount() const {
    return duplicate_edge_count_;
}

std::size_t CompactDepGraph::MaxIndegree() const {
    return max_indegree_;
}

double CompactDepGraph::AverageIndegree() const {
    if (node_weights_.empty()) {
        return 0.0;
    }
    return static_cast<double>(parent_ids_.size()) / static_cast<double>(node_weights_.size());
}

bool CompactDepGraph::TopologicalOrderInvariant() const {
    return topological_order_invariant_;
}

qret::Json CompactDepGraph::ProfileStats() const {
    auto extra = qret::Json::object();
    extra["node_count"] = node_weights_.size();
    extra["edge_count"] = parent_ids_.size();
    extra["parent_offsets_size"] = parent_offsets_.size();
    extra["parent_offsets_capacity"] = parent_offsets_.capacity();
    extra["parent_ids_size"] = parent_ids_.size();
    extra["parent_ids_capacity"] = parent_ids_.capacity();
    extra["edge_lengths_size"] = edge_lengths_.size();
    extra["edge_lengths_capacity"] = edge_lengths_.capacity();
    extra["node_weights_size"] = node_weights_.size();
    extra["node_weights_capacity"] = node_weights_.capacity();
    extra["working_dp_size"] = working_dp_.size();
    extra["working_dp_capacity"] = working_dp_.capacity();
    extra["parent_offsets_capacity_bytes"] =
            parent_offsets_.capacity() * sizeof(std::uint32_t);
    extra["parent_ids_capacity_bytes"] = parent_ids_.capacity() * sizeof(IdType);
    extra["edge_lengths_capacity_bytes"] = edge_lengths_.capacity() * sizeof(Length);
    extra["node_weights_capacity_bytes"] = node_weights_.capacity() * sizeof(Weight);
    extra["working_dp_capacity_bytes"] = working_dp_.capacity() * sizeof(std::uint64_t);
    extra["temporary_dedup_buffer_max_size"] = max_indegree_;
    extra["duplicate_edge_count"] = duplicate_edge_count_;
    extra["maximum_indegree"] = max_indegree_;
    extra["average_indegree"] = AverageIndegree();
    extra["topological_order_invariant"] = topological_order_invariant_;
    extra["finalized"] = finalized_;
    return extra;
}

void CompactDepGraph::SealCurrentNodeIfNeeded() {
    if (!current_node_open_) {
        return;
    }
    if (parent_ids_.size() > std::numeric_limits<std::uint32_t>::max()) {
        throw std::overflow_error("CompactDepGraph edge offset overflow.");
    }
    parent_offsets_.push_back(static_cast<std::uint32_t>(parent_ids_.size()));
    current_node_open_ = false;
}

void CompactDepGraph::CheckFinalized() const {
    if (!finalized_) {
        throw std::logic_error("CompactDepGraph must be finalized before querying.");
    }
}

void CompactDepGraph::CheckNode(IdType id) const {
    if (id >= node_weights_.size()) {
        throw std::out_of_range("CompactDepGraph node is not found.");
    }
}

namespace {
enum class DepGraphImplementation : std::uint8_t {
    Legacy,
    LegacyNoId2Ptr,
    LegacyDense,
    Compact,
};

DepGraphImplementation ParseDepGraphImplementation() {
    const auto* raw = std::getenv("QRET_DEP_GRAPH_IMPL");
    if (raw == nullptr || std::string(raw).empty() || std::string(raw) == "compact") {
        return DepGraphImplementation::Compact;
    }
    const auto value = std::string(raw);
    if (value == "legacy") {
        return DepGraphImplementation::Legacy;
    }
    if (value == "legacy_no_id2ptr") {
        return DepGraphImplementation::LegacyNoId2Ptr;
    }
    if (value == "legacy_dense") {
        return DepGraphImplementation::LegacyDense;
    }
    throw std::runtime_error(
            fmt::format(
                    "Invalid QRET_DEP_GRAPH_IMPL '{}'. Expected one of: legacy, "
                    "legacy_no_id2ptr, legacy_dense, compact.",
                    value
            )
    );
}

std::string ToString(DepGraphImplementation mode) {
    switch (mode) {
        case DepGraphImplementation::Legacy:
            return "legacy";
        case DepGraphImplementation::LegacyNoId2Ptr:
            return "legacy_no_id2ptr";
        case DepGraphImplementation::LegacyDense:
            return "legacy_dense";
        case DepGraphImplementation::Compact:
            return "compact";
        default:
            break;
    }
    throw std::runtime_error("unknown DepGraphImplementation");
}

bool UsesLegacyGraph(DepGraphImplementation mode) {
    return mode == DepGraphImplementation::Legacy
            || mode == DepGraphImplementation::LegacyNoId2Ptr
            || mode == DepGraphImplementation::LegacyDense;
}

bool StoresPtrMap(DepGraphImplementation mode) {
    return mode == DepGraphImplementation::Legacy
            || mode == DepGraphImplementation::LegacyNoId2Ptr;
}

bool StoresIdMap(DepGraphImplementation mode) {
    return mode == DepGraphImplementation::Legacy;
}
}  // namespace

struct DepGraph::Impl {
    explicit Impl(DepGraphImplementation tmp_mode)
        : mode(tmp_mode) {}

    void AddNode(IdType id, Weight weight, const ScLsInstructionBase& inst) {
        if (UsesLegacyGraph(mode)) {
            legacy_graph.AddNode(id, weight);
            if (StoresPtrMap(mode)) {
                ptr2id[&inst] = id;
            }
            if (StoresIdMap(mode)) {
                id2ptr[id] = &inst;
            }
        } else {
            const auto compact_id = compact_graph.AddNode(weight);
            if (compact_id != id) {
                throw std::logic_error("CompactDepGraph dense ID invariant failed.");
            }
        }
    }

    void AddEdge(IdType from, IdType to, Length length = 0) {
        if (UsesLegacyGraph(mode)) {
            legacy_graph.AddEdge(from, to, length);
        } else {
            compact_graph.AddEdgeToCurrentNode(from, length);
        }
    }

    void Finalize() {
        if (UsesLegacyGraph(mode)) {
            const auto is_dag = legacy_graph.Topsort();
            if (!is_dag) {
                throw std::logic_error("instruction graph is not DAG");
            }
        } else {
            compact_graph.Finalize();
        }
    }

    DepGraphImplementation mode;
    std::map<const ScLsInstructionBase*, IdType> ptr2id = {};
    std::map<IdType, const ScLsInstructionBase*> id2ptr = {};
    DiGraph legacy_graph = {};
    CompactDepGraph compact_graph = {};
};

DepGraph::DepGraph(const MachineFunction& mf)
    : impl_(std::make_unique<Impl>(ParseDepGraphImplementation())) {
    const auto& target = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());

    auto q2id = std::map<QSymbol, IdType>();
    auto c2id = std::map<CSymbol, IdType>();
    for (CSymbol::IdType i = 0; i < NumReservedCSymbols; ++i) {
        c2id[CSymbol{i}] = std::numeric_limits<IdType>::max();
    }
    auto measurement_c = std::unordered_set<CSymbol>{};

    auto add_edge = [&q2id, &c2id, &measurement_c, &target, this](
                            const IdType id,
                            const ScLsInstructionBase& inst
                    ) {
        // Check qtarget.
        for (const auto& q : inst.QTarget()) {
            if (q2id.contains(q)) {
                const auto old = q2id.at(q);
                impl_->AddEdge(old, id);
            }
            q2id[q] = id;
        }

        // Check Move and MoveTrans.
        if (const auto* i = DynCast<Move>(&inst)) {
            const auto src = i->Qubit();
            const auto dst = i->QDest();
            if (src != dst) {
                q2id.erase(src);
                q2id[dst] = id;
            }
        } else if (const auto* i = DynCast<MoveTrans>(&inst)) {
            const auto src = i->Qubit();
            const auto dst = i->QDest();
            if (src != dst) {
                q2id.erase(src);
                q2id[dst] = id;
            }
        }

        // Check condition.
        for (const auto& c : inst.Condition()) {
            const auto old = c2id.at(c);
            if (measurement_c.contains(c)) {
                impl_->AddEdge(old, id, target.machine_option.reaction_time);
            } else if (c.Id() >= NumReservedCSymbols) {
                impl_->AddEdge(old, id, 0);
            }
        }

        // Check CDepend.
        for (const auto& c : inst.CDepend()) {
            if (!c2id.contains(c)) {
                throw std::runtime_error(
                        fmt::format(
                                "Compile info calculation error: Dependant classical symbol {} is "
                                "not allocated ({}) ",
                                c.ToString(),
                                inst.ToString()
                        )
                );
            }
            const auto old = c2id.at(c);
            if (measurement_c.contains(c)) {
                impl_->AddEdge(old, id, target.machine_option.reaction_time);
            } else if (c.Id() >= NumReservedCSymbols) {
                impl_->AddEdge(old, id, 0);
            }
        }

        // Check ccreate.
        for (const auto& c : inst.CCreate()) {
            if (c2id.contains(c)) {
                throw std::runtime_error(
                        fmt::format(
                                "Compile info calculation error: Cannot store values "
                                "into the same "
                                "classical symbol ({}) ({}).",
                                c.ToString(),
                                inst.ToString()
                        )
                );
            }
            c2id[c] = id;
            if (inst.IsMeasurement()) {
                measurement_c.emplace(c);
            }
        }
    };

    auto id = IdType{0};
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            impl_->AddNode(id, inst.Latency(), inst);
            add_edge(id, inst);
            ++id;
        }
    }

    impl_->Finalize();
}

DepGraph::~DepGraph() = default;
DepGraph::DepGraph(DepGraph&&) noexcept = default;
DepGraph& DepGraph::operator=(DepGraph&&) noexcept = default;

void DepGraph::SetInstWeight(const ScLsInstructionBase& inst, Weight weight) {
    if (!StoresPtrMap(impl_->mode)) {
        throw std::logic_error("SetInstWeight requires a DepGraph pointer map.");
    }
    SetNodeWeight(impl_->ptr2id.at(&inst), weight);
}

void DepGraph::SetNodeWeight(IdType id, Weight weight) {
    if (UsesLegacyGraph(impl_->mode)) {
        impl_->legacy_graph.SetNodeWeight(id, weight);
    } else {
        impl_->compact_graph.SetNodeWeight(id, weight);
    }
}

void DepGraph::SetAllLength(Length length) {
    if (UsesLegacyGraph(impl_->mode)) {
        for (const auto& node : impl_->legacy_graph) {
            for (const auto& from : node.parent) {
                impl_->legacy_graph.SetEdgeLength(from, node.id, length);
            }
        }
    } else {
        impl_->compact_graph.SetAllLength(length);
    }
}

void DepGraph::SetLength(
        const ScLsInstructionBase& from,
        const ScLsInstructionBase& to,
        Length length
) {
    if (!StoresPtrMap(impl_->mode)) {
        throw std::logic_error("SetLength by instruction requires a DepGraph pointer map.");
    }
    SetLength(impl_->ptr2id.at(&from), impl_->ptr2id.at(&to), length);
}

void DepGraph::SetLength(IdType from, IdType to, Length length) {
    if (UsesLegacyGraph(impl_->mode)) {
        impl_->legacy_graph.SetEdgeLength(from, to, length);
    } else {
        impl_->compact_graph.SetLength(from, to, length);
    }
}

DepGraph::Weight DepGraph::CalcHeaviest() const {
    if (UsesLegacyGraph(impl_->mode)) {
        const auto& [weight, _path, _depth_of_each_node] = FindHeaviestPath(impl_->legacy_graph);
        return weight;
    }
    return impl_->compact_graph.CalcHeaviest();
}

DepGraph::Length DepGraph::CalcLongest() const {
    if (UsesLegacyGraph(impl_->mode)) {
        const auto& [length, _path, _depth_of_each_node] = FindLongestPath(impl_->legacy_graph);
        return length;
    }
    return impl_->compact_graph.CalcLongest();
}

std::size_t DepGraph::NumNodes() const {
    return UsesLegacyGraph(impl_->mode) ? impl_->legacy_graph.NumNodes()
                                        : impl_->compact_graph.NumNodes();
}

std::size_t DepGraph::NumEdges() const {
    return UsesLegacyGraph(impl_->mode) ? impl_->legacy_graph.NumEdges()
                                        : impl_->compact_graph.NumEdges();
}

std::size_t DepGraph::PointerMapSize() const {
    return impl_->ptr2id.size();
}

std::size_t DepGraph::IdMapSize() const {
    return impl_->id2ptr.size();
}

std::string DepGraph::ImplementationMode() const {
    return ToString(impl_->mode);
}

qret::Json DepGraph::ProfileStats() const {
    auto extra = qret::Json::object();
    extra["dep_graph_implementation"] = ImplementationMode();
    extra["dep_graph_object_size_bytes"] = sizeof(DepGraph);
    extra["dep_graph_nodes"] = NumNodes();
    extra["dep_graph_edges"] = NumEdges();
    extra["dep_graph_ptr2id_size"] = PointerMapSize();
    extra["dep_graph_id2ptr_size"] = IdMapSize();
    if (UsesLegacyGraph(impl_->mode)) {
        extra["dep_graph_node_estimated_payload_bytes"] = NumNodes() * sizeof(DiGraph::Node);
        extra["dep_graph_edge_estimated_payload_bytes"] = NumEdges() * sizeof(DiGraph::Edge);
        extra["dep_graph_pointer_map_estimated_payload_bytes"] =
                PointerMapSize() * (sizeof(const ScLsInstructionBase*) + sizeof(IdType))
                + IdMapSize() * (sizeof(IdType) + sizeof(const ScLsInstructionBase*));
        extra["topological_order_invariant"] = true;
        return extra;
    }

    auto compact = impl_->compact_graph.ProfileStats();
    for (auto it = compact.begin(); it != compact.end(); ++it) {
        extra[fmt::format("compact_{}", it.key())] = it.value();
    }
    return extra;
}

class StateWithoutTopology {
public:
    StateWithoutTopology() {
        // Add reserved symbols.
        for (CSymbol::IdType i = 0; i < NumReservedCSymbols; ++i) {
            c_[CSymbol{i}] = Beat{0};
        }
    }

    void Step(const ScLsFixedV0MachineOption& option) {
        for (auto&& [_, state] : mf_state_) {
            StepMagicFactoryState(option, state);
        }
        for (auto&& [_, state] : ef_state_) {
            StepEntanglementFactoryState(option, state);
        }
    }

    void AddQubit(Beat b, QSymbol q) {
        if (q_.contains(q)) {
            throw std::runtime_error(
                    fmt::format(
                            "Compile info calculation error: Cannot allocate already allocated "
                            "qubit symbol ({}).",
                            q.ToString()
                    )
            );
        }
        q_[q] = b;
    }
    void DelQubit(QSymbol q) {
        if (!q_.contains(q)) {
            throw std::runtime_error(
                    fmt::format(
                            "Compile info calculation error: Cannot use not allocated qubit symbol "
                            "({}).",
                            q
                    )
            );
        }
        q_.erase(q);
    }
    /**
     * @brief CSymbol @p c becomes available at beat @p available.
     *
     * @param available
     * @param c
     */
    void AddRegister(Beat available, CSymbol c) {
        if (c_.contains(c)) {
            throw std::runtime_error(
                    fmt::format(
                            "Compile info calculation error: Cannot store values into the same "
                            "classical symbol ({}).",
                            c.ToString()
                    )
            );
        }
        c_[c] = available;
    }
    void AddMagicFactory(const ScLsFixedV0MachineOption& option, MSymbol m) {
        if (mf_state_.contains(m)) {
            throw std::runtime_error(
                    fmt::format(
                            "Compile info calculation error: Cannot allocate already allocated "
                            "magic state factory ({}).",
                            m.ToString()
                    )
            );
        }
        mf_state_[m] = MagicFactoryState::Empty(option.magic_factory_seed_offset + m.Id());
    }
    void AddEntanglementFactory(ESymbol e1, ESymbol e2) {
        for (const auto e : {e1, e2}) {
            if (ef_state_.contains(e)) {
                throw std::runtime_error(
                        fmt::format(
                                "Compile info calculation error: Cannot allocate already allocated "
                                "entanglement factory ({}).",
                                e.ToString()
                        )
                );
            }
        }
        ef_state_[e1] = EntanglementFactoryState::Empty();
        ef_state_[e2] = EntanglementFactoryState::Empty();
        ef_pair_[e1] = e2;
        ef_pair_[e2] = e1;
    }

    bool IsConditionSatisfied(Beat b, const std::list<CSymbol>& condition) const {
        for (const auto c : condition) {
            if (!IsCAvailable(b, c)) {
                return false;
            }
        }
        return true;
    }

    bool IsQAvailable(Beat b, QSymbol q) const {
        if (!q_.contains(q)) {
            throw std::runtime_error(
                    fmt::format(
                            "Compile info calculation error: Cannot use not allocated qubit symbol "
                            "({}).",
                            q.ToString()
                    )
            );
        }
        return q_.at(q) <= b;
    }
    bool IsCAvailable(Beat b, CSymbol c) const {
        if (!c_.contains(c)) {
            throw std::runtime_error(
                    fmt::format(
                            "Compile info calculation error: Cannot use not allocated classical "
                            "symbol ({}).",
                            c.ToString()
                    )
            );
        }
        return c_.at(c) <= b;
    }
    bool IsMagicAvailable() const {
        for (const auto& [_, state] : mf_state_) {
            if (state.IsAvailable()) {
                return true;
            }
        }
        return false;
    }
    bool IsEntanglementAvailable(EHandle eh) const {
        if (eh_es_.contains(eh)) {
            return true;
        }
        for (const auto& [_, state] : ef_state_) {
            if (state.IsAvailable()) {
                return true;
            }
        }
        return false;
    }

    bool TryUseTarget(Beat b, const ScLsInstructionBase* inst) {
        for (const auto q : inst->QTarget()) {
            if (!IsQAvailable(b, q)) {
                return false;
            }
        }
        if (inst->UseMagicState() && !IsMagicAvailable()) {
            return false;
        }
        if (inst->UseEntanglement()) {
            const auto eh = inst->EHTarget().front();
            if (!IsEntanglementAvailable(eh)) {
                return false;
            }
        }

        // Use.
        if (const auto* i = DynCast<Move>(inst)) {
            const auto src = i->Qubit();
            const auto dst = i->QDest();
            UseQ(b + inst->Latency(), dst);
            if (src != dst) {
                DelQubit(src);
            }
        } else if (const auto* i = DynCast<MoveTrans>(inst)) {
            const auto src = i->Qubit();
            const auto dst = i->QDest();
            UseQ(b + inst->Latency(), dst);
            if (src != dst) {
                DelQubit(src);
            }
        } else {
            for (const auto q : inst->QTarget()) {
                UseQ(b + inst->Latency(), q);
            }
        }
        if (inst->UseMagicState()) {
            UseMagic();
        }
        if (inst->UseEntanglement()) {
            const auto eh = inst->EHTarget().front();
            UseEntanglementAvailable(eh);
        }

        return true;
    }

private:
    void UseQ(Beat use_until, QSymbol q) {
        q_[q] = use_until;
    }
    void UseMagic() {
        for (auto&& [m, state] : mf_state_) {
            if (state.TryUseMagic()) {
                return;
            }
        }

        throw std::runtime_error("Compile info calculation error: Cannot use empty magic factory.");
    }
    void UseEntanglementAvailable(EHandle eh) {
        // Handle is already created.
        if (eh_es_.contains(eh)) {
            const auto [e1, e2] = eh_es_.at(eh);
            ef_state_.at(e1).UseHandle(eh);
            ef_state_.at(e2).UseHandle(eh);
            return;
        }

        // Use entanglement pair and create entanglement handle.
        for (auto&& [e1, state] : ef_state_) {
            if (state.IsAvailable()) {
                state.AddHandle(eh);
                const auto e2 = ef_pair_.at(e1);
                ef_state_.at(e2).AddHandle(eh);
                eh_es_[eh] = {e1, e2};
                return;
            }
        }

        throw std::runtime_error(
                "Compile info calculation error: Cannot use empty entanglement factory."
        );
    }

    std::unordered_map<QSymbol, Beat> q_;
    std::unordered_map<CSymbol, Beat> c_;
    std::unordered_map<MSymbol, MagicFactoryState> mf_state_;
    std::unordered_map<ESymbol, EntanglementFactoryState> ef_state_;
    std::unordered_map<ESymbol, ESymbol> ef_pair_;
    std::unordered_map<EHandle, std::pair<ESymbol, ESymbol>> eh_es_;
};

Beat CalcRuntimeWithoutTopology(MachineFunction& mf) {
    static constexpr auto InstQueuePeekSize = 2000;

    const auto& machine = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());
    const auto& option = machine.machine_option;

    MarkCompileInfoStage("calc_runtime_without_topology_entry", mf);
    auto state = StateWithoutTopology{};
    auto queue = InstQueue(option, mf, InstQueue::WeightAlgorithm::InvDepth);
    MarkCompileInfoStage(
            "calc_runtime_without_topology_after_queue_construct",
            mf,
            nullptr,
            InstQueueStats(queue)
    );
    queue.Peek(InstQueuePeekSize);
    MarkCompileInfoStage(
            "calc_runtime_without_topology_after_initial_peek",
            mf,
            nullptr,
            InstQueueStats(queue)
    );
    auto current_beat = Beat{0};
    auto runtime = Beat{0};
    auto idle_beats = Beat{0};
    while (!queue.Empty()) {
        // Peek instructions if needed.
        if (!queue.IsPeekFinished() && queue.NumInsts() < InstQueuePeekSize) {
            queue.Peek(InstQueuePeekSize);
        }

        ScLsInstructionBase* run_instruction = nullptr;
        for (auto* base_inst : queue) {
            // Check if base_inst is runnable or note.
            // If runnable, update state, set run_instruction and break this loop.

            if (!state.IsConditionSatisfied(current_beat, base_inst->Condition())) {
                continue;
            }

            if (auto* inst = DynCast<Allocate>(base_inst)) {
                const auto q = inst->Qubit();
                state.AddQubit(current_beat, q);
                run_instruction = base_inst;
            } else if (auto* inst = DynCast<DeAllocate>(base_inst)) {
                const auto q = inst->Qubit();
                state.DelQubit(q);
                run_instruction = base_inst;
            } else if (auto* inst = DynCast<AllocateMagicFactory>(base_inst)) {
                const auto m = inst->MagicFactory();
                state.AddMagicFactory(option, m);
                run_instruction = base_inst;
            } else if (auto* inst = DynCast<AllocateEntanglementFactory>(base_inst)) {
                const auto e1 = inst->EntanglementFactory1();
                const auto e2 = inst->EntanglementFactory2();
                state.AddEntanglementFactory(e1, e2);
                run_instruction = base_inst;
            } else if (auto* inst = DynCast<ClassicalOperation>(base_inst)) {
                auto runnable = true;
                for (const auto c : inst->RegisterList()) {
                    if (!state.IsCAvailable(current_beat, c)) {
                        runnable = false;
                        break;
                    }
                }
                if (runnable) {
                    state.AddRegister(current_beat, inst->CDest());
                    run_instruction = base_inst;
                }
            } else {
                if (state.TryUseTarget(current_beat, base_inst)) {
                    run_instruction = base_inst;
                    if (!base_inst->CCreate().empty()) {
                        state.AddRegister(
                                current_beat + option.reaction_time + base_inst->StartCorrecting(),
                                base_inst->CCreate().front()
                        );
                    }
                }
            }

            if (run_instruction != nullptr) {
                break;
            }
        }

        if (run_instruction != nullptr) {
            queue.Run(run_instruction);
            idle_beats = 0;
            runtime = std::max(runtime, current_beat + run_instruction->Latency());
        } else {
            // If no instructions are runnable, step beat.
            ++current_beat;
            ++idle_beats;
            queue.SetBeat(current_beat);
            state.Step(option);
        }

        // Throw error if some instruction is not runnable for a long beats.
        if (idle_beats >= AllowedMaxIdleBeats(option)) {
            auto ss = std::stringstream();
            ss << "Compile info calculation error: Do not process any instructions for "
               << idle_beats << " beats\n";
            ss << "Routing pass failed to satisfy the following instructions:\n";
            for (const auto* inst : queue) {
                ss << "  * " << inst->ToString() << "\n";
            }
            throw std::runtime_error(ss.str());
        }
    }

    auto exit_extra = InstQueueStats(queue);
    exit_extra["runtime_without_topology"] = runtime;
    exit_extra["current_beat"] = current_beat;
    MarkCompileInfoStage("calc_runtime_without_topology_exit", mf, nullptr, exit_extra);
    return runtime;
}

TimeSeries::TimeSeries(const MachineFunction& mf) {
    const auto& target = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());
    const auto machine_instruction_count = CountMachineInstructions(mf);
    const auto runtime = CalculateTimeSeriesRuntime(mf);

    // Initialize beat2chip_ and beat2inst_
    beat2inst_.resize(runtime);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_beat2inst_resize",
            mf,
            nullptr,
            TimeSeriesStats(*this, machine_instruction_count)
    );
    beat2chip_.resize(runtime);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_beat2chip_resize",
            mf,
            nullptr,
            TimeSeriesStats(*this, machine_instruction_count)
    );

    // Set beat2inst_
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            const auto& metadata = inst.Metadata();

            const auto latency = EffectiveTimeSeriesLatency(inst);
            for (auto beat = metadata.beat; beat < metadata.beat + latency; ++beat) {
                beat2inst_[beat].emplace_back(&inst);
            }
        }
    }
    MarkCompileInfoStage(
            "calc_info_with_topology_after_beat2inst_fill",
            mf,
            nullptr,
            TimeSeriesStats(*this, machine_instruction_count)
    );

    // Calculate beat2chip_
    for (auto beat = Beat{0}; beat < beat2inst_.size(); ++beat) {
        const auto& insts = beat2inst_[beat];

        auto& chip_info = beat2chip_[beat];
        if (beat == 0) {
            InitializeChipInfoSpace(chip_info, target);
        } else {
            chip_info = beat2chip_[beat - 1];
            chip_info.used_ancilla_count = 0;
        }

        for (const auto& inst : insts) {
            ApplyInstructionToChipInfo(chip_info, *inst);
        }
    }
    MarkCompileInfoStage(
            "calc_info_with_topology_after_beat2chip_fill",
            mf,
            nullptr,
            TimeSeriesStats(*this, machine_instruction_count)
    );
}

std::size_t TimeSeries::InstructionPointerCount() const {
    auto ret = std::size_t{0};
    for (const auto& insts : beat2inst_) {
        ret += insts.size();
    }
    return ret;
}

std::size_t TimeSeries::InstructionPointerCapacity() const {
    auto ret = std::size_t{0};
    for (const auto& insts : beat2inst_) {
        ret += insts.capacity();
    }
    return ret;
}

CompactTimeSeries::CompactTimeSeries(const MachineFunction& mf) {
    const auto& target = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());
    const auto machine_instruction_count = CountMachineInstructions(mf);
    const auto runtime = CalculateTimeSeriesRuntime(mf);

    auto beat_counts = std::vector<std::size_t>(runtime, 0);
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            const auto latency = EffectiveTimeSeriesLatency(inst);
            for (auto beat = inst.Metadata().beat; beat < inst.Metadata().beat + latency; ++beat) {
                ++beat_counts[beat];
            }
        }
    }

    beat_offsets_.resize(runtime + 1, 0);
    for (auto beat = std::size_t{0}; beat < runtime; ++beat) {
        beat_offsets_[beat + 1] = beat_offsets_[beat] + beat_counts[beat];
    }
    instruction_ptrs_.resize(beat_offsets_.back());
    auto cursor = beat_offsets_;
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            const auto latency = EffectiveTimeSeriesLatency(inst);
            for (auto beat = inst.Metadata().beat; beat < inst.Metadata().beat + latency; ++beat) {
                instruction_ptrs_[cursor[beat]++] = &inst;
            }
        }
    }
    MarkCompileInfoStage(
            "calc_info_with_topology_after_compact_beat2inst_fill",
            mf,
            nullptr,
            TimeSeriesStats(*this, machine_instruction_count)
    );

    beat2chip_.resize(runtime);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_compact_beat2chip_resize",
            mf,
            nullptr,
            TimeSeriesStats(*this, machine_instruction_count)
    );
    for (auto beat = Beat{0}; beat < beat2chip_.size(); ++beat) {
        auto& chip_info = beat2chip_[beat];
        if (beat == 0) {
            InitializeChipInfoSpace(chip_info, target);
        } else {
            chip_info = beat2chip_[beat - 1];
            chip_info.used_ancilla_count = 0;
        }
        for (const auto* inst : GetInstructions(beat)) {
            ApplyInstructionToChipInfo(chip_info, *inst);
        }
    }
    MarkCompileInfoStage(
            "calc_info_with_topology_after_compact_beat2chip_fill",
            mf,
            nullptr,
            TimeSeriesStats(*this, machine_instruction_count)
    );
}

struct FeedbackInfo {
    Beat beat;
    bool counted;
};

std::map<CSymbol, FeedbackInfo> InitialFeedbackInfo() {
    auto feedback_info = std::map<CSymbol, FeedbackInfo>();
    for (std::uint64_t i = 0; i < NumReservedCSymbols; ++i) {
        feedback_info.emplace(CSymbol{i}, FeedbackInfo{.beat = 0, .counted = false});
    }
    return feedback_info;
}

template <typename InstructionRange>
void ProcessFeedbackCreates(
        Beat beat,
        const InstructionRange& insts,
        std::map<CSymbol, FeedbackInfo>& feedback_info
) {
    for (const auto* inst : insts) {
        for (const auto& c : inst->CCreate()) {
            if (feedback_info.contains(c)) {
                throw std::runtime_error(fmt::format(
                        "Store the measurement results to the same c-symbol ({}) more than once",
                        c.ToString()
                ));
            }
            feedback_info.emplace(c, FeedbackInfo{beat + inst->StartCorrecting(), false});
        }
    }
}

template <typename InstructionRange, typename FeedbackCounter>
void ProcessFeedbackConditions(
        const InstructionRange& insts,
        std::map<CSymbol, FeedbackInfo>& feedback_info,
        FeedbackCounter&& count_feedback
) {
    for (const auto* inst : insts) {
        for (const auto& c : inst->Condition()) {
            if (!feedback_info.contains(c)) {
                throw std::runtime_error(fmt::format(
                        "Instruction ({}) is conditioned by unknown c-symbol ({})",
                        inst->ToString(),
                        c.ToString()
                ));
            }

            auto& info = feedback_info.at(c);
            if (!info.counted) {
                count_feedback(info.beat);
                info.counted = true;
            }
        }
    }
}

void ResetTopologyTimeSeriesFields(ScLsFixedV0CompileInfo& compile_info) {
    compile_info.gate_throughput = {};
    compile_info.gate_throughput_summary = {};
    compile_info.measurement_feedback_rate = {};
    compile_info.measurement_feedback_rate_summary = {};
    compile_info.magic_state_consumption_rate = {};
    compile_info.magic_state_consumption_rate_summary = {};
    compile_info.entanglement_consumption_rate = {};
    compile_info.entanglement_consumption_rate_summary = {};
    compile_info.chip_cell_algorithmic_qubit = {};
    compile_info.chip_cell_algorithmic_qubit_summary = {};
    compile_info.chip_cell_algorithmic_qubit_ratio = {};
    compile_info.chip_cell_algorithmic_qubit_ratio_summary = {};
    compile_info.chip_cell_active_qubit_area = {};
    compile_info.chip_cell_active_qubit_area_summary = {};
    compile_info.chip_cell_active_qubit_area_ratio = {};
    compile_info.chip_cell_active_qubit_area_ratio_summary = {};
    compile_info.qubit_volume = 0;
}

template <typename Series>
void FillFullVectorsFromSeries(
        const MachineFunction& mf,
        ScLsFixedV0CompileInfo& compile_info,
        const Series& time_series,
        SummaryTimeSeriesImplementation summary_impl
) {
    const auto machine_instruction_count = CountMachineInstructions(mf);
    auto with_time_series_stats = [&](qret::Json extra = qret::Json::object()) {
        auto ret = CompileInfoModeStats(CompileInfoOutputMode::Full, summary_impl);
        const auto time_series_stats = TimeSeriesStats(time_series, machine_instruction_count);
        for (auto it = time_series_stats.begin(); it != time_series_stats.end(); ++it) {
            ret[it.key()] = it.value();
        }
        for (auto it = extra.begin(); it != extra.end(); ++it) {
            ret[it.key()] = it.value();
        }
        return ret;
    };

    MarkCompileInfoStage(
            "calc_info_with_topology_before_compile_info_vector_resize",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.gate_throughput.resize(compile_info.runtime, 0);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_vector_resize_gate_throughput",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.measurement_feedback_rate.resize(compile_info.runtime, 0);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_vector_resize_measurement_feedback_rate",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.magic_state_consumption_rate.resize(compile_info.runtime, 0);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_vector_resize_magic_state_consumption_rate",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.entanglement_consumption_rate.resize(compile_info.runtime, 0);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_vector_resize_entanglement_consumption_rate",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_after_rate_vector_resize",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.chip_cell_algorithmic_qubit.resize(compile_info.runtime);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_vector_resize_chip_cell_algorithmic_qubit",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.chip_cell_algorithmic_qubit_ratio.resize(compile_info.runtime);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_vector_resize_chip_cell_algorithmic_qubit_ratio",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.chip_cell_active_qubit_area.resize(compile_info.runtime);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_vector_resize_chip_cell_active_qubit_area",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.chip_cell_active_qubit_area_ratio.resize(compile_info.runtime);
    MarkCompileInfoStage(
            "calc_info_with_topology_after_vector_resize_chip_cell_active_qubit_area_ratio",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_after_cell_vector_resize",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_after_all_vector_resize",
            mf,
            &compile_info,
            with_time_series_stats()
    );

    MarkCompileInfoStage(
            "calc_info_with_topology_before_time_series_fill",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    auto feedback_info = InitialFeedbackInfo();
    for (auto beat = Beat{0}; beat < compile_info.runtime; ++beat) {
        const auto insts = time_series.GetInstructions(beat);
        compile_info.gate_throughput[beat] = insts.size();
        ProcessFeedbackCreates(beat, insts, feedback_info);
        ProcessFeedbackConditions(insts, feedback_info, [&](Beat feedback_beat) {
            compile_info.measurement_feedback_rate[feedback_beat]++;
        });

        for (const auto* inst : insts) {
            if (inst->UseMagicState()) {
                compile_info.magic_state_consumption_rate[beat]++;
            }
            if (inst->UseEntanglement()) {
                compile_info.entanglement_consumption_rate[beat] += inst->CountEntanglement();
            }
        }
    }
    auto rate_extra = qret::Json::object();
    rate_extra["feedback_info_size"] = feedback_info.size();
    rate_extra["feedback_info_estimated_payload_bytes"] =
            feedback_info.size() * (sizeof(CSymbol) + sizeof(FeedbackInfo));
    MarkCompileInfoStage(
            "calc_info_with_topology_after_rate_fill",
            mf,
            &compile_info,
            with_time_series_stats(rate_extra)
    );

    compile_info.chip_cell_count = time_series.GetChipInfo(0).ChipCellCount();
    for (auto beat = Beat{0}; beat < compile_info.runtime; ++beat) {
        compile_info.chip_cell_algorithmic_qubit[beat] =
                time_series.GetChipInfo(beat).ChipCellAlgorithmicQubit();
        compile_info.chip_cell_algorithmic_qubit_ratio[beat] =
                time_series.GetChipInfo(beat).ChipCellAlgorithmicQubitRatio();
        compile_info.chip_cell_active_qubit_area[beat] =
                time_series.GetChipInfo(beat).ChipCellActiveQubitArea();
        compile_info.chip_cell_active_qubit_area_ratio[beat] =
                time_series.GetChipInfo(beat).ChipCellActiveQubitAreaRatio();
    }
    MarkCompileInfoStage(
            "calc_info_with_topology_after_cell_fill",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    compile_info.qubit_volume = std::accumulate(
            compile_info.chip_cell_active_qubit_area.begin(),
            compile_info.chip_cell_active_qubit_area.end(),
            std::uint64_t{0}
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_after_time_series_fill",
            mf,
            &compile_info,
            with_time_series_stats()
    );
}

template <typename Series>
void FillSummaryStatsFromSeries(
        const MachineFunction& mf,
        ScLsFixedV0CompileInfo& compile_info,
        const Series& time_series,
        SummaryTimeSeriesImplementation summary_impl
) {
    const auto machine_instruction_count = CountMachineInstructions(mf);
    auto with_time_series_stats = [&](qret::Json extra = qret::Json::object()) {
        auto ret = CompileInfoModeStats(CompileInfoOutputMode::Summary, summary_impl);
        const auto time_series_stats = TimeSeriesStats(time_series, machine_instruction_count);
        for (auto it = time_series_stats.begin(); it != time_series_stats.end(); ++it) {
            ret[it.key()] = it.value();
        }
        for (auto it = extra.begin(); it != extra.end(); ++it) {
            ret[it.key()] = it.value();
        }
        return ret;
    };

    MarkCompileInfoStage(
            "calc_info_with_topology_before_summary_accumulation",
            mf,
            &compile_info,
            with_time_series_stats()
    );
    auto feedback_info = InitialFeedbackInfo();
    auto measurement_feedback_by_beat = std::map<Beat, std::uint64_t>();
    auto measurement_feedback_sum = std::uint64_t{0};
    auto measurement_feedback_peak = std::uint64_t{0};
    for (auto beat = Beat{0}; beat < compile_info.runtime; ++beat) {
        const auto insts = time_series.GetInstructions(beat);
        compile_info.gate_throughput_summary.Add(static_cast<std::uint64_t>(insts.size()));

        ProcessFeedbackCreates(beat, insts, feedback_info);
        ProcessFeedbackConditions(insts, feedback_info, [&](Beat feedback_beat) {
            auto& count = measurement_feedback_by_beat[feedback_beat];
            ++count;
            ++measurement_feedback_sum;
            measurement_feedback_peak = std::max(measurement_feedback_peak, count);
        });

        auto magic_rate = std::uint64_t{0};
        auto entanglement_rate = std::uint64_t{0};
        for (const auto* inst : insts) {
            if (inst->UseMagicState()) {
                ++magic_rate;
            }
            if (inst->UseEntanglement()) {
                entanglement_rate += inst->CountEntanglement();
            }
        }
        compile_info.magic_state_consumption_rate_summary.Add(magic_rate);
        compile_info.entanglement_consumption_rate_summary.Add(entanglement_rate);

        const auto& chip = time_series.GetChipInfo(beat);
        const auto algorithmic_qubit =
                static_cast<std::uint64_t>(chip.ChipCellAlgorithmicQubit());
        const auto algorithmic_qubit_ratio = chip.ChipCellAlgorithmicQubitRatio();
        const auto active_qubit_area =
                static_cast<std::uint64_t>(chip.ChipCellActiveQubitArea());
        const auto active_qubit_area_ratio = chip.ChipCellActiveQubitAreaRatio();
        compile_info.chip_cell_algorithmic_qubit_summary.Add(algorithmic_qubit);
        compile_info.chip_cell_algorithmic_qubit_ratio_summary.Add(algorithmic_qubit_ratio);
        compile_info.chip_cell_active_qubit_area_summary.Add(active_qubit_area);
        compile_info.chip_cell_active_qubit_area_ratio_summary.Add(active_qubit_area_ratio);
        compile_info.qubit_volume += active_qubit_area;
    }

    compile_info.measurement_feedback_rate_summary.Set(
            measurement_feedback_sum,
            measurement_feedback_peak,
            compile_info.runtime
    );
    compile_info.chip_cell_count = time_series.GetChipInfo(0).ChipCellCount();

    auto summary_extra = qret::Json::object();
    summary_extra["feedback_info_size"] = feedback_info.size();
    summary_extra["feedback_info_estimated_payload_bytes"] =
            feedback_info.size() * (sizeof(CSymbol) + sizeof(FeedbackInfo));
    summary_extra["measurement_feedback_nonzero_beats"] = measurement_feedback_by_beat.size();
    summary_extra["measurement_feedback_sparse_map_estimated_payload_bytes"] =
            measurement_feedback_by_beat.size() * (sizeof(Beat) + sizeof(std::uint64_t));
    MarkCompileInfoStage(
            "calc_info_with_topology_after_summary_accumulation",
            mf,
            &compile_info,
            with_time_series_stats(summary_extra)
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_after_summary_stats_store",
            mf,
            &compile_info,
            with_time_series_stats(summary_extra)
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_before_time_series_destroy",
            mf,
            &compile_info,
            with_time_series_stats(summary_extra)
    );
}

struct EventSweepStorage {
    std::vector<const ScLsInstructionBase*> instructions;
    std::vector<std::uint32_t> start_indices;
    std::vector<std::uint32_t> end_indices;
};

Beat EventSweepStartBeat(const EventSweepStorage& storage, std::uint32_t index) {
    return storage.instructions[index]->Metadata().beat;
}

Beat EventSweepEndBeat(const EventSweepStorage& storage, std::uint32_t index) {
    const auto& inst = *storage.instructions[index];
    return inst.Metadata().beat + EffectiveTimeSeriesLatency(inst);
}

qret::Json EventSweepStorageStats(
        const EventSweepStorage& storage,
        std::uint64_t runtime,
        std::size_t active_set_size = 0,
        std::size_t active_set_peak = 0
) {
    auto extra = qret::Json::object();
    extra["time_series_storage_impl"] = "event_sweep";
    extra["time_series_runtime"] = runtime;
    extra["beat2inst_bucket_count"] = 0;
    extra["beat2inst_bucket_capacity"] = 0;
    extra["beat2inst_outer_size"] = 0;
    extra["beat2inst_outer_capacity"] = 0;
    extra["beat2inst_inner_vector_sizeof"] = sizeof(std::vector<const ScLsInstructionBase*>);
    extra["beat2inst_bucket_object_bytes"] = 0;
    extra["beat2inst_outer_control_block_capacity_bytes"] = 0;
    extra["beat2inst_pointer_count"] = 0;
    extra["beat2inst_pointer_capacity"] = 0;
    extra["beat2inst_pointer_payload_bytes"] = 0;
    extra["beat2inst_pointer_capacity_bytes"] = 0;
    extra["beat2chip_count"] = 0;
    extra["beat2chip_capacity"] = 0;
    extra["beat2chip_size"] = 0;
    extra["beat2chip_sizeof_element_bytes"] = sizeof(TimeSeries::ChipInfo);
    extra["beat2chip_payload_bytes"] = 0;
    extra["beat2chip_capacity_bytes"] = 0;
    extra["event_sweep_instruction_count"] = storage.instructions.size();
    extra["event_sweep_instruction_pointer_capacity_bytes"] =
            storage.instructions.capacity() * sizeof(const ScLsInstructionBase*);
    extra["event_sweep_start_index_count"] = storage.start_indices.size();
    extra["event_sweep_start_index_capacity_bytes"] =
            storage.start_indices.capacity() * sizeof(std::uint32_t);
    extra["event_sweep_end_index_count"] = storage.end_indices.size();
    extra["event_sweep_end_index_capacity_bytes"] =
            storage.end_indices.capacity() * sizeof(std::uint32_t);
    extra["event_sweep_active_set_size"] = active_set_size;
    extra["event_sweep_active_set_peak"] = active_set_peak;
    extra["event_sweep_estimated_capacity_bytes"] =
            extra["event_sweep_instruction_pointer_capacity_bytes"].get<std::size_t>()
            + extra["event_sweep_start_index_capacity_bytes"].get<std::size_t>()
            + extra["event_sweep_end_index_capacity_bytes"].get<std::size_t>();
    return extra;
}

EventSweepStorage BuildEventSweepStorage(const MachineFunction& mf) {
    auto storage = EventSweepStorage();
    storage.instructions = CollectInstructionPointers(mf);
    if (storage.instructions.size() > std::numeric_limits<std::uint32_t>::max()) {
        throw std::overflow_error("summary event-sweep instruction index overflow");
    }
    storage.start_indices.resize(storage.instructions.size());
    storage.end_indices.resize(storage.instructions.size());
    std::iota(storage.start_indices.begin(), storage.start_indices.end(), std::uint32_t{0});
    std::iota(storage.end_indices.begin(), storage.end_indices.end(), std::uint32_t{0});

    std::sort(storage.start_indices.begin(), storage.start_indices.end(), [&](auto lhs, auto rhs) {
        const auto lhs_beat = EventSweepStartBeat(storage, lhs);
        const auto rhs_beat = EventSweepStartBeat(storage, rhs);
        return lhs_beat < rhs_beat || (lhs_beat == rhs_beat && lhs < rhs);
    });
    std::sort(storage.end_indices.begin(), storage.end_indices.end(), [&](auto lhs, auto rhs) {
        const auto lhs_beat = EventSweepEndBeat(storage, lhs);
        const auto rhs_beat = EventSweepEndBeat(storage, rhs);
        return lhs_beat < rhs_beat || (lhs_beat == rhs_beat && lhs < rhs);
    });
    return storage;
}

void RunEventSweepSummary(
        const MachineFunction& mf,
        ScLsFixedV0CompileInfo& compile_info,
        std::vector<SummaryBeatMetrics>* debug_beats = nullptr
) {
    const auto& target = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());
    const auto runtime = CalculateTimeSeriesRuntime(mf);
    compile_info.runtime = runtime;
    if (debug_beats != nullptr) {
        debug_beats->assign(runtime, SummaryBeatMetrics{});
    }

    auto storage = BuildEventSweepStorage(mf);
    auto mode_extra = CompileInfoModeStats(
            CompileInfoOutputMode::Summary,
            SummaryTimeSeriesImplementation::EventSweep
    );
    auto storage_extra = EventSweepStorageStats(storage, runtime);
    for (auto it = storage_extra.begin(); it != storage_extra.end(); ++it) {
        mode_extra[it.key()] = it.value();
    }
    MarkCompileInfoStage(
            "calc_info_with_topology_after_event_sweep_index_build",
            mf,
            &compile_info,
            mode_extra
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_before_summary_accumulation",
            mf,
            &compile_info,
            mode_extra
    );

    auto feedback_info = InitialFeedbackInfo();
    auto measurement_feedback_by_beat = std::map<Beat, std::uint64_t>();
    auto measurement_feedback_sum = std::uint64_t{0};
    auto measurement_feedback_peak = std::uint64_t{0};
    auto active = std::set<std::uint32_t>();
    auto active_peak = std::size_t{0};
    auto start_pos = std::size_t{0};
    auto end_pos = std::size_t{0};
    auto chip = TimeSeries::ChipInfo();
    auto insts = std::vector<const ScLsInstructionBase*>();

    for (auto beat = Beat{0}; beat < runtime; ++beat) {
        while (end_pos < storage.end_indices.size()
               && EventSweepEndBeat(storage, storage.end_indices[end_pos]) == beat) {
            active.erase(storage.end_indices[end_pos]);
            ++end_pos;
        }
        while (start_pos < storage.start_indices.size()
               && EventSweepStartBeat(storage, storage.start_indices[start_pos]) == beat) {
            active.insert(storage.start_indices[start_pos]);
            ++start_pos;
        }
        active_peak = std::max(active_peak, active.size());

        if (beat == 0) {
            InitializeChipInfoSpace(chip, target);
        } else {
            chip.used_ancilla_count = 0;
        }

        insts.clear();
        if (insts.capacity() < active.size()) {
            insts.reserve(active.size());
        }
        for (const auto index : active) {
            insts.emplace_back(storage.instructions[index]);
        }
        compile_info.gate_throughput_summary.Add(static_cast<std::uint64_t>(insts.size()));

        ProcessFeedbackCreates(beat, insts, feedback_info);
        ProcessFeedbackConditions(insts, feedback_info, [&](Beat feedback_beat) {
            auto& count = measurement_feedback_by_beat[feedback_beat];
            ++count;
            ++measurement_feedback_sum;
            measurement_feedback_peak = std::max(measurement_feedback_peak, count);
            if (debug_beats != nullptr && feedback_beat < debug_beats->size()) {
                (*debug_beats)[feedback_beat].measurement_feedback_rate++;
            }
        });

        auto magic_rate = std::uint64_t{0};
        auto entanglement_rate = std::uint64_t{0};
        for (const auto* inst : insts) {
            if (inst->UseMagicState()) {
                ++magic_rate;
            }
            if (inst->UseEntanglement()) {
                entanglement_rate += inst->CountEntanglement();
            }
        }
        compile_info.magic_state_consumption_rate_summary.Add(magic_rate);
        compile_info.entanglement_consumption_rate_summary.Add(entanglement_rate);

        for (const auto* inst : insts) {
            ApplyInstructionToChipInfo(chip, *inst);
        }
        const auto algorithmic_qubit =
                static_cast<std::uint64_t>(chip.ChipCellAlgorithmicQubit());
        const auto algorithmic_qubit_ratio = chip.ChipCellAlgorithmicQubitRatio();
        const auto active_qubit_area =
                static_cast<std::uint64_t>(chip.ChipCellActiveQubitArea());
        const auto active_qubit_area_ratio = chip.ChipCellActiveQubitAreaRatio();
        compile_info.chip_cell_algorithmic_qubit_summary.Add(algorithmic_qubit);
        compile_info.chip_cell_algorithmic_qubit_ratio_summary.Add(algorithmic_qubit_ratio);
        compile_info.chip_cell_active_qubit_area_summary.Add(active_qubit_area);
        compile_info.chip_cell_active_qubit_area_ratio_summary.Add(active_qubit_area_ratio);
        compile_info.qubit_volume += active_qubit_area;
        if (beat == 0) {
            compile_info.chip_cell_count = chip.ChipCellCount();
        }

        if (debug_beats != nullptr) {
            auto& debug = (*debug_beats)[beat];
            debug.instructions = insts;
            debug.chip_info = chip;
            debug.gate_throughput = debug.instructions.size();
            debug.magic_state_consumption_rate = magic_rate;
            debug.entanglement_consumption_rate = entanglement_rate;
        }
    }

    compile_info.measurement_feedback_rate_summary.Set(
            measurement_feedback_sum,
            measurement_feedback_peak,
            runtime
    );

    auto summary_extra = EventSweepStorageStats(storage, runtime, active.size(), active_peak);
    summary_extra["feedback_info_size"] = feedback_info.size();
    summary_extra["feedback_info_estimated_payload_bytes"] =
            feedback_info.size() * (sizeof(CSymbol) + sizeof(FeedbackInfo));
    summary_extra["measurement_feedback_nonzero_beats"] = measurement_feedback_by_beat.size();
    summary_extra["measurement_feedback_sparse_map_estimated_payload_bytes"] =
            measurement_feedback_by_beat.size() * (sizeof(Beat) + sizeof(std::uint64_t));
    auto final_extra = CompileInfoModeStats(
            CompileInfoOutputMode::Summary,
            SummaryTimeSeriesImplementation::EventSweep
    );
    for (auto it = summary_extra.begin(); it != summary_extra.end(); ++it) {
        final_extra[it.key()] = it.value();
    }
    MarkCompileInfoStage(
            "calc_info_with_topology_after_summary_accumulation",
            mf,
            &compile_info,
            final_extra
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_after_summary_stats_store",
            mf,
            &compile_info,
            final_extra
    );
    MarkCompileInfoStage(
            "calc_info_with_topology_before_time_series_destroy",
            mf,
            &compile_info,
            final_extra
    );
}

template <typename Series>
std::vector<SummaryBeatMetrics> CollectSeriesBeatMetrics(const MachineFunction& mf) {
    const auto series = Series(mf);
    auto ret = std::vector<SummaryBeatMetrics>(series.GetRuntime());
    auto feedback_info = InitialFeedbackInfo();
    for (auto beat = Beat{0}; beat < series.GetRuntime(); ++beat) {
        const auto insts = series.GetInstructions(beat);
        auto& row = ret[beat];
        row.instructions.assign(insts.begin(), insts.end());
        row.chip_info = series.GetChipInfo(beat);
        row.gate_throughput = row.instructions.size();
        ProcessFeedbackCreates(beat, row.instructions, feedback_info);
        ProcessFeedbackConditions(row.instructions, feedback_info, [&](Beat feedback_beat) {
            if (feedback_beat < ret.size()) {
                ret[feedback_beat].measurement_feedback_rate++;
            }
        });
        for (const auto* inst : row.instructions) {
            if (inst->UseMagicState()) {
                ++row.magic_state_consumption_rate;
            }
            if (inst->UseEntanglement()) {
                row.entanglement_consumption_rate += inst->CountEntanglement();
            }
        }
    }
    return ret;
}

std::vector<SummaryBeatMetrics> CollectLegacyTimeSeriesBeatMetrics(const MachineFunction& mf) {
    return CollectSeriesBeatMetrics<TimeSeries>(mf);
}

std::vector<SummaryBeatMetrics> CollectCompactTimeSeriesBeatMetrics(const MachineFunction& mf) {
    return CollectSeriesBeatMetrics<CompactTimeSeries>(mf);
}

std::vector<SummaryBeatMetrics> CollectEventSweepBeatMetrics(const MachineFunction& mf) {
    auto info = ScLsFixedV0CompileInfo();
    auto ret = std::vector<SummaryBeatMetrics>();
    RunEventSweepSummary(mf, info, &ret);
    return ret;
}

ScLsFixedV0CompileInfo CalculateEventSweepSummaryForTest(const MachineFunction& mf) {
    auto info = ScLsFixedV0CompileInfo();
    ResetTopologyTimeSeriesFields(info);
    RunEventSweepSummary(mf, info);
    return info;
}

bool CompileInfoWithoutTopology::RunOnMachineFunction(MachineFunction& mf) {
    LOG_INFO("Calculate compile information without topology.");
    MarkCompileInfoStage("calc_info_without_topology_entry", mf);
    if (!mf.HasCompileInfo()) {
        LOG_INFO("Initialize compile information.");
        InitCompileInfo().RunOnMachineFunction(mf);
    }

    Validate(mf);

    const auto& target = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());
    auto& compile_info = *static_cast<ScLsFixedV0CompileInfo*>(mf.GetMutCompileInfo());
    MarkCompileInfoStage("calc_info_without_topology_after_validate", mf, &compile_info);

    // gate_count, gate_count_dict, magic_state_consumption_count, magic_factory_count
    compile_info.gate_count = 0;
    compile_info.gate_count_dict.clear();
    compile_info.magic_state_consumption_count = 0;
    compile_info.magic_factory_count = 0;
    compile_info.entanglement_consumption_count = 0;
    compile_info.entanglement_factory_count = 0;
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            compile_info.gate_count++;

            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            const auto type = inst.Type();
            if (compile_info.gate_count_dict.contains(type)) {
                compile_info.gate_count_dict[inst.Type()]++;
            } else {
                compile_info.gate_count_dict.insert({type, 1});
            }

            if (inst.UseMagicState()) {
                compile_info.magic_state_consumption_count++;
            }
            if (inst.UseEntanglement()) {
                compile_info.entanglement_consumption_count += inst.CountEntanglement();
            }

            if (type == ScLsInstructionType::ALLOCATE_MAGIC_FACTORY) {
                compile_info.magic_factory_count++;
            }
            if (type == ScLsInstructionType::ALLOCATE_ENTANGLEMENT_FACTORY) {
                compile_info.entanglement_factory_count++;
            }
        }
    }
    MarkCompileInfoStage("calc_info_without_topology_after_instruction_scan", mf, &compile_info);

    // runtime_estimation_magic_state_consumption_count
    compile_info.runtime_estimation_magic_state_consumption_count =
            compile_info.magic_state_consumption_count
            * target.machine_option.magic_generation_period;

    if (compile_info.entanglement_consumption_count % 2 != 0) {
        LOG_ERROR(
                "Entanglement consumption count: {}",
                compile_info.entanglement_consumption_count
        );
        throw std::logic_error("Entanglement consumption count must be even.");
    }
    compile_info.entanglement_consumption_count /= 2;
    // runtime_estimation_entanglement_consumption_count
    compile_info.runtime_estimation_entanglement_consumption_count =
            compile_info.entanglement_consumption_count
            * target.machine_option.entanglement_generation_period;

    // dependency graph of instruction
    MarkCompileInfoStage("calc_info_without_topology_before_dep_graph", mf, &compile_info);
    auto graph = DepGraph(mf);
    MarkCompileInfoStage(
            "calc_info_without_topology_after_dep_graph",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );

    // runtime_without_topology
    MarkCompileInfoStage(
            "calc_info_without_topology_before_runtime_without_topology",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );
    compile_info.runtime_without_topology = CalcRuntimeWithoutTopology(mf);
    MarkCompileInfoStage(
            "calc_info_without_topology_after_runtime_without_topology",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );

    // gate_depth
    auto inst_id = DepGraph::IdType{0};
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            graph.SetNodeWeight(inst_id, inst.Latency() == 0 ? 0 : 1);
            ++inst_id;
        }
    }
    compile_info.gate_depth = graph.CalcHeaviest();
    MarkCompileInfoStage(
            "calc_info_without_topology_after_gate_depth",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );

    // magic_state_consumption_depth
    inst_id = DepGraph::IdType{0};
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            graph.SetNodeWeight(inst_id, inst.UseMagicState() ? 1 : 0);
            ++inst_id;
        }
    }
    compile_info.magic_state_consumption_depth = graph.CalcHeaviest();

    // runtime_estimation_magic_state_consumption_depth
    compile_info.runtime_estimation_magic_state_consumption_depth =
            compile_info.magic_state_consumption_depth
            * target.machine_option.magic_generation_period;
    MarkCompileInfoStage(
            "calc_info_without_topology_after_magic_depth",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );

    // entanglement_consumption_depth
    inst_id = DepGraph::IdType{0};
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            graph.SetNodeWeight(inst_id, inst.UseEntanglement() ? 1 : 0);
            ++inst_id;
        }
    }
    compile_info.entanglement_consumption_depth = graph.CalcHeaviest();

    // runtime_estimation_entanglement_consumption_depth
    compile_info.runtime_estimation_entanglement_consumption_depth =
            compile_info.entanglement_consumption_depth
            * target.machine_option.entanglement_generation_period;
    MarkCompileInfoStage(
            "calc_info_without_topology_after_entanglement_depth",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );

    // measurement_feedback_count, runtime_estimation_measurement_feedback_count
    compile_info.measurement_feedback_count = [&mf]() {
        auto feedback = std::set<CSymbol>();
        for (const auto& bb : mf) {
            for (const auto& minst : bb) {
                const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
                for (const auto& c : inst.Condition()) {
                    feedback.insert(c);
                }
            }
        }
        return feedback.size();
    }();
    compile_info.runtime_estimation_measurement_feedback_count =
            compile_info.measurement_feedback_count * target.machine_option.reaction_time;
    MarkCompileInfoStage(
            "calc_info_without_topology_after_measurement_feedback_count",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );

    // measurement_feedback_depth
    {
        graph.SetAllLength(0);

        struct FeedbackSource {
            DepGraph::IdType id = 0;
            bool is_measurement = false;
        };

        auto c2inst = std::map<CSymbol, std::optional<FeedbackSource>>();
        for (CSymbol::IdType i = 0; i < NumReservedCSymbols; ++i) {
            c2inst[CSymbol{i}] = std::nullopt;
        }
        inst_id = DepGraph::IdType{0};
        for (const auto& bb : mf) {
            for (const auto& minst : bb) {
                const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());

                // If condition is measurement result, set length to 1.
                for (const auto& c : inst.Condition()) {
                    const auto& from = c2inst.at(c);
                    if (from.has_value() && from->is_measurement) {
                        // Measurement.
                        graph.SetLength(from->id, inst_id, 1);
                    }
                }

                // Check CDepend.
                for (const auto& c : inst.CDepend()) {
                    const auto& from = c2inst.at(c);
                    if (from.has_value() && from->is_measurement) {
                        // c is measurement result.
                        graph.SetLength(from->id, inst_id, 1);
                    }
                }

                // Check CCreate.
                for (const auto& c : inst.CCreate()) {
                    c2inst[c] = FeedbackSource{.id = inst_id, .is_measurement = inst.IsMeasurement()};
                }
                ++inst_id;
            }
        }
    }
    compile_info.measurement_feedback_depth = graph.CalcLongest();
    MarkCompileInfoStage(
            "calc_info_without_topology_after_measurement_feedback_depth",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );

    // runtime_estimation_measurement_feedback_depth
    compile_info.runtime_estimation_measurement_feedback_depth =
            compile_info.measurement_feedback_depth * target.machine_option.reaction_time;

    MarkCompileInfoStage(
            "calc_info_without_topology_exit",
            mf,
            &compile_info,
            DepGraphStats(graph)
    );
    return false;
}

bool CompileInfoWithTopology::RunOnMachineFunction(MachineFunction& mf) {
    LOG_INFO("Calculate compile information with topology.");
    const auto output_mode = CompileInfoOutputModeFromString(CompileInfoOutputModeOption.Get());
    const auto summary_impl = ParseSummaryTimeSeriesImplementation();
    const auto keep_full_vectors =
            output_mode == CompileInfoOutputMode::Full
            || summary_impl == SummaryTimeSeriesImplementation::Vector;
    MarkCompileInfoStage(
            "calc_info_with_topology_entry",
            mf,
            nullptr,
            CompileInfoModeStats(output_mode, summary_impl)
    );
    if (!mf.HasCompileInfo()) {
        LOG_INFO("Initialize compile information.");
        InitCompileInfo().RunOnMachineFunction(mf);
    }

    Validate(mf);

    auto& compile_info = *static_cast<ScLsFixedV0CompileInfo*>(mf.GetMutCompileInfo());
    MarkCompileInfoStage(
            "calc_info_with_topology_after_validate",
            mf,
            &compile_info,
            CompileInfoModeStats(output_mode, summary_impl)
    );

    ResetTopologyTimeSeriesFields(compile_info);

    MarkCompileInfoStage(
            "calc_info_with_topology_before_time_series_construct",
            mf,
            &compile_info,
            CompileInfoModeStats(output_mode, summary_impl)
    );

    if (keep_full_vectors || summary_impl == SummaryTimeSeriesImplementation::LegacyTimeSeries) {
        MarkCompileInfoStage(
                "calc_info_with_topology_before_time_series",
                mf,
                &compile_info,
                CompileInfoModeStats(output_mode, summary_impl)
        );
        const auto time_series = TimeSeries(mf);
        const auto machine_instruction_count = CountMachineInstructions(mf);
        auto time_series_extra = TimeSeriesStats(time_series, machine_instruction_count);
        auto mode_extra = CompileInfoModeStats(output_mode, summary_impl);
        for (auto it = time_series_extra.begin(); it != time_series_extra.end(); ++it) {
            mode_extra[it.key()] = it.value();
        }
        MarkCompileInfoStage(
                "calc_info_with_topology_after_time_series_construct",
                mf,
                &compile_info,
                mode_extra
        );
        MarkCompileInfoStage(
                "calc_info_with_topology_after_time_series",
                mf,
                &compile_info,
                mode_extra
        );

        // runtime
        compile_info.runtime = time_series.GetRuntime();

        if (compile_info.runtime == 0) {
            auto empty_extra = TimeSeriesStats(time_series, machine_instruction_count);
            auto empty_mode_extra = CompileInfoModeStats(output_mode, summary_impl);
            for (auto it = empty_extra.begin(); it != empty_extra.end(); ++it) {
                empty_mode_extra[it.key()] = it.value();
            }
            MarkCompileInfoStage(
                    "calc_info_with_topology_exit_empty_runtime",
                    mf,
                    &compile_info,
                    empty_mode_extra
            );
            MarkCompileInfoStage(
                    "calc_info_with_topology_before_time_series_destroy",
                    mf,
                    &compile_info,
                    empty_mode_extra
            );
            return false;
        }

        if (keep_full_vectors) {
            FillFullVectorsFromSeries(mf, compile_info, time_series, summary_impl);
        } else {
            FillSummaryStatsFromSeries(mf, compile_info, time_series, summary_impl);
        }
        MarkCompileInfoStage(
                "calc_info_with_topology_after_time_series_destroy",
                mf,
                &compile_info,
                CompileInfoModeStats(output_mode, summary_impl)
        );
    } else if (summary_impl == SummaryTimeSeriesImplementation::CompactTimeSeries) {
        const auto time_series = CompactTimeSeries(mf);
        compile_info.runtime = time_series.GetRuntime();
        FillSummaryStatsFromSeries(mf, compile_info, time_series, summary_impl);
        MarkCompileInfoStage(
                "calc_info_with_topology_after_time_series_destroy",
                mf,
                &compile_info,
                CompileInfoModeStats(output_mode, summary_impl)
        );
    } else if (summary_impl == SummaryTimeSeriesImplementation::EventSweep) {
        RunEventSweepSummary(mf, compile_info);
        MarkCompileInfoStage(
                "calc_info_with_topology_after_time_series_destroy",
                mf,
                &compile_info,
                CompileInfoModeStats(output_mode, summary_impl)
        );
    } else {
        throw std::invalid_argument("unsupported summary time-series implementation");
    }
    MarkCompileInfoStage(
            "calc_info_with_topology_exit",
            mf,
            &compile_info,
            CompileInfoModeStats(output_mode, summary_impl)
    );
    return false;
}

std::uint64_t CompileInfoWithQecResourceEstimation::EstimateMinimumCodeDistance(
        double p,
        double lambda,
        double eps,
        std::uint64_t active_volume
) {
    const auto valid = p > 0.0 && eps > 0.0 && active_volume > 0 && lambda > 0.0 && lambda < 1.0;
    if (!valid) {
        const auto msg = fmt::format(
                "Invalid parameters for estimating code distance: "
                "p={}, lambda={}, eps={}, active_volume={}",
                p,
                lambda,
                eps,
                active_volume
        );
        throw std::runtime_error(msg);
    }

    const auto ratio = eps / (p * static_cast<double>(active_volume));
    if (!std::isfinite(ratio) || ratio <= 0.0) {
        const auto msg = fmt::format(
                "Invalid ratio for estimating code distance: ratio={}, p={}, lambda={}, "
                "eps={}, "
                "active_volume={}",
                ratio,
                p,
                lambda,
                eps,
                active_volume
        );
        throw std::runtime_error(msg);
    }
    if (ratio >= 1.0) {
        return 1;
    }

    const auto log_lambda = std::log(lambda);
    const auto log_ratio = std::log(ratio);
    if (!std::isfinite(log_lambda) || !std::isfinite(log_ratio) || log_lambda >= 0.0) {
        const auto msg = fmt::format(
                "Invalid logs for estimating code distance: log_lambda={}, log_ratio={}",
                log_lambda,
                log_ratio
        );
        throw std::runtime_error(msg);
    }

    const auto exponent = log_ratio / log_lambda;
    const auto ceil_exp = static_cast<std::uint64_t>(std::ceil(exponent));
    return (2 * ceil_exp) + 1;
}
double CompileInfoWithQecResourceEstimation::EstimateExecutionTimeSec(
        std::uint64_t d,
        std::uint64_t runtime,
        double t_cycle
) {
    return static_cast<double>(runtime) * static_cast<double>(d) * t_cycle;
}
std::uint64_t CompileInfoWithQecResourceEstimation::EstimatePhysicalQubitCount(
        std::uint64_t d,
        std::uint64_t chip_cell_count
) {
    return d * d * chip_cell_count * 2;
}

bool CompileInfoWithQecResourceEstimation::RunOnMachineFunction(MachineFunction& mf) {
    auto& compile_info = *static_cast<ScLsFixedV0CompileInfo*>(mf.GetMutCompileInfo());
    const auto& target = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());
    const auto& option = target.machine_option;

    try {
        compile_info.code_distance = EstimateMinimumCodeDistance(
                option.physical_error_rate,
                option.drop_rate,
                option.allowed_failure_prob,
                compile_info.qubit_volume
        );
        compile_info.execution_time_sec = EstimateExecutionTimeSec(
                compile_info.code_distance,
                compile_info.runtime,
                option.code_cycle_time_sec
        );
        compile_info.num_physical_qubits = EstimatePhysicalQubitCount(
                compile_info.code_distance,
                compile_info.chip_cell_count
        );
    } catch (const std::runtime_error& error) {
        LOG_ERROR("{}", error.what());
    }

    return false;
}

bool InitCompileInfo::RunOnMachineFunction(MachineFunction& mf) {
    LOG_INFO("Initialize compile information");
    MarkCompileInfoStage("init_compile_info_entry", mf);
    mf.InitializeCompileInfo(std::unique_ptr<ScLsFixedV0CompileInfo>(new ScLsFixedV0CompileInfo()));

    const auto& target = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());
    auto& compile_info = *static_cast<ScLsFixedV0CompileInfo*>(mf.GetMutCompileInfo());

    // Initialize constants.
    compile_info.use_magic_state_cultivation = target.machine_option.use_magic_state_cultivation;
    compile_info.magic_factory_seed_offset = target.machine_option.magic_factory_seed_offset;
    compile_info.magic_generation_period = target.machine_option.magic_generation_period;
    compile_info.prob_magic_state_creation = target.machine_option.prob_magic_state_creation;
    compile_info.maximum_magic_state_stock = target.machine_option.maximum_magic_state_stock;
    compile_info.entanglement_generation_period =
            target.machine_option.entanglement_generation_period;
    compile_info.maximum_entangled_state_stock =
            target.machine_option.maximum_entangled_state_stock;
    compile_info.reaction_time = target.machine_option.reaction_time;
    compile_info.topology = target.topology;

    MarkCompileInfoStage("init_compile_info_exit", mf, &compile_info);
    return false;
}

bool DumpCompileInfo::RunOnMachineFunction(MachineFunction& mf) {
    LOG_INFO("Dump compile information");
    MarkCompileInfoStage("dump_compile_info_entry", mf);
    if (!mf.HasCompileInfo()) {
        LOG_ERROR(
                "MachineFunction does not have compile information. Run "
                "sc_ls_fixed_v0::calc_info_without_topology and/or "
                "sc_ls_fixed_v0::calc_info_with_topology before "
                "running sc_ls_fixed_v0::dump_compile_info."
        );
        return false;
    }

    const auto& compile_info = *static_cast<const ScLsFixedV0CompileInfo*>(mf.GetCompileInfo());
    MarkCompileInfoStage("dump_compile_info_after_compile_info_ref", mf, &compile_info);
    MarkCompileInfoStage("dump_compile_info_before_stdout", mf, &compile_info);
    std::cout << compile_info << std::endl;
    MarkCompileInfoStage("dump_compile_info_after_stdout", mf, &compile_info);

    if (!DumpCompileInfoToJson.Get().empty()) {
        const auto& path = DumpCompileInfoToJson.Get();
        const auto output_mode = CompileInfoOutputModeFromString(CompileInfoOutputModeOption.Get());
        auto fs = std::ofstream(path);
        if (fs.good()) {
            if (qret::rss_profile::Enabled()) {
                auto json_start_extra = MachineAndCompileInfoStats(mf, &compile_info);
                json_start_extra["json_output_path"] = path;
                json_start_extra["compile_info_output_mode"] = std::string(ToString(output_mode));
                qret::rss_profile::Mark("before_serialization", json_start_extra);
                qret::rss_profile::Mark(
                        "dump_compile_info_before_json_dom_create",
                        json_start_extra
                );
                {
                    auto j = compile_info.Json(output_mode);
                    auto json_extra = MachineAndCompileInfoStats(mf, &compile_info);
                    json_extra["json_output_path"] = path;
                    json_extra["compile_info_output_mode"] = std::string(ToString(output_mode));
                    json_extra["json_dom"] = JsonValueStats(j);
                    qret::rss_profile::Mark(
                            "dump_compile_info_after_json_dom_create",
                            json_extra
                    );

                    qret::rss_profile::Mark(
                            "dump_compile_info_before_json_stream_write",
                            json_extra
                    );
                    fs << j << std::endl;
                    fs.flush();
                    auto write_extra = json_extra;
                    write_extra["stream_good"] = fs.good();
                    qret::rss_profile::Mark(
                            "dump_compile_info_after_json_stream_write",
                            write_extra
                    );
                    qret::rss_profile::Mark("after_serialization", write_extra);
                }
                auto after_destroy_extra = MachineAndCompileInfoStats(mf, &compile_info);
                after_destroy_extra["json_output_path"] = path;
                after_destroy_extra["compile_info_output_mode"] =
                        std::string(ToString(output_mode));
                qret::rss_profile::Mark(
                        "dump_compile_info_after_json_dom_destroy",
                        after_destroy_extra
                );
            } else {
                fs << compile_info.Json(output_mode) << std::endl;
            }
        } else {
            LOG_ERROR("Failed to open: {}", path);
        }
    }
    if (!DumpCompileInfoToMarkdown.Get().empty()) {
        const auto& path = DumpCompileInfoToMarkdown.Get();
        auto fs = std::ofstream(DumpCompileInfoToMarkdown.Get());
        if (fs.good()) {
            fs << compile_info.Markdown() << std::endl;
        } else {
            LOG_ERROR("Failed to open: {}", path);
        }
    }
    MarkCompileInfoStage("dump_compile_info_exit", mf, &compile_info);
    return false;
}
}  // namespace qret::sc_ls_fixed_v0
