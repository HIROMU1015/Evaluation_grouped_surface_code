/**
 * @file qret/target/sc_ls_fixed_v0/calc_compile_info.h
 * @brief Calculate compile information.
 */

#ifndef QRET_TARGET_SC_LS_FIXED_V0_CALC_COMPILE_INFO_H
#define QRET_TARGET_SC_LS_FIXED_V0_CALC_COMPILE_INFO_H

#include <fmt/format.h>
#include <fmt/ostream.h>

#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <vector>

#include "qret/base/graph.h"
#include "qret/base/json.h"
#include "qret/codegen/machine_function.h"
#include "qret/codegen/machine_function_pass.h"
#include "qret/qret_export.h"
#include "qret/target/sc_ls_fixed_v0/compile_info.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"

namespace qret::sc_ls_fixed_v0 {
class QRET_EXPORT CompactDepGraph {
public:
    using IdType = DiGraph::IdType;
    using Weight = DiGraph::Weight;
    using Length = DiGraph::Length;

    CompactDepGraph();

    IdType AddNode(Weight weight = 0);
    void AddEdgeToCurrentNode(IdType from, Length length = 0);
    void Finalize();

    void SetNodeWeight(IdType id, Weight weight);
    void SetAllLength(Length length);
    void SetLength(IdType from, IdType to, Length length);

    [[nodiscard]] Weight CalcHeaviest() const;
    [[nodiscard]] Length CalcLongest() const;

    [[nodiscard]] std::size_t NumNodes() const;
    [[nodiscard]] std::size_t NumEdges() const;
    [[nodiscard]] std::size_t DuplicateEdgeCount() const;
    [[nodiscard]] std::size_t MaxIndegree() const;
    [[nodiscard]] double AverageIndegree() const;
    [[nodiscard]] bool TopologicalOrderInvariant() const;
    [[nodiscard]] qret::Json ProfileStats() const;

private:
    void SealCurrentNodeIfNeeded();
    void CheckFinalized() const;
    void CheckNode(IdType id) const;

    std::vector<Weight> node_weights_;
    std::vector<std::uint32_t> parent_offsets_;
    std::vector<IdType> parent_ids_;
    std::vector<Length> edge_lengths_;
    mutable std::vector<std::uint64_t> working_dp_;
    std::size_t duplicate_edge_count_ = 0;
    std::size_t max_indegree_ = 0;
    bool current_node_open_ = false;
    bool finalized_ = false;
    bool topological_order_invariant_ = true;
};

class QRET_EXPORT DepGraph {
public:
    using IdType = DiGraph::IdType;
    using Weight = DiGraph::Weight;
    using Length = DiGraph::Length;

    explicit DepGraph(const MachineFunction& mf);
    ~DepGraph();
    DepGraph(const DepGraph&) = delete;
    DepGraph& operator=(const DepGraph&) = delete;
    DepGraph(DepGraph&&) noexcept;
    DepGraph& operator=(DepGraph&&) noexcept;

    void SetInstWeight(const ScLsInstructionBase& inst, Weight weight);
    void SetNodeWeight(IdType id, Weight weight);
    void SetAllLength(Length length);
    void SetLength(const ScLsInstructionBase& from, const ScLsInstructionBase& to, Length length);
    void SetLength(IdType from, IdType to, Length length);

    [[nodiscard]] Weight CalcHeaviest() const;
    [[nodiscard]] Length CalcLongest() const;
    [[nodiscard]] std::size_t NumNodes() const;
    [[nodiscard]] std::size_t NumEdges() const;
    [[nodiscard]] std::size_t PointerMapSize() const;
    [[nodiscard]] std::size_t IdMapSize() const;
    [[nodiscard]] std::string ImplementationMode() const;
    [[nodiscard]] qret::Json ProfileStats() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
class QRET_EXPORT TimeSeries {
public:
    struct ChipInfo {
        std::uint32_t space = 0;
        std::uint32_t m_symb = 0;
        std::uint32_t e_symb = 0;
        std::uint32_t q_symb = 0;
        std::uint32_t used_ancilla_count = 0;

        std::uint32_t ChipCellCount() const {
            return space - m_symb - e_symb;
        }
        std::uint32_t ChipCellAlgorithmicQubit() const {
            return q_symb;
        }
        double ChipCellAlgorithmicQubitRatio() const {
            return static_cast<double>(ChipCellAlgorithmicQubit())
                    / static_cast<double>(ChipCellCount());
        }
        std::uint32_t ChipCellActiveQubitArea() const {
            return used_ancilla_count + q_symb;
        }
        double ChipCellActiveQubitAreaRatio() const {
            return static_cast<double>(ChipCellActiveQubitArea())
                    / static_cast<double>(ChipCellCount());
        }
    };

    explicit TimeSeries(const MachineFunction& mf);

    std::uint64_t GetRuntime() const {
        assert(beat2chip_.size() == beat2chip_.size());
        return beat2chip_.size();
    }
    const std::vector<const ScLsInstructionBase*>& GetInstructions(std::uint64_t beat) const {
        return beat2inst_[beat];
    }
    const ChipInfo& GetChipInfo(std::uint64_t beat) const {
        return beat2chip_[beat];
    }
    std::size_t InstructionBucketCount() const {
        return beat2inst_.size();
    }
    std::size_t InstructionBucketCapacity() const {
        return beat2inst_.capacity();
    }
    std::size_t InstructionPointerCount() const;
    std::size_t InstructionPointerCapacity() const;
    std::size_t ChipInfoCount() const {
        return beat2chip_.size();
    }
    std::size_t ChipInfoCapacity() const {
        return beat2chip_.capacity();
    }

    auto begin() const {
        return beat2chip_.begin();
    }
    auto cbegin() const {
        return beat2chip_.cbegin();
    }
    auto end() const {
        return beat2chip_.end();
    }
    auto cend() const {
        return beat2chip_.cend();
    }

private:
    std::vector<std::vector<const ScLsInstructionBase*>> beat2inst_;
    std::vector<ChipInfo> beat2chip_;
};

class QRET_EXPORT CompactTimeSeries {
public:
    using InstructionPointer = const ScLsInstructionBase*;

    explicit CompactTimeSeries(const MachineFunction& mf);

    std::uint64_t GetRuntime() const {
        return beat_offsets_.empty() ? 0 : beat_offsets_.size() - 1;
    }
    std::span<const InstructionPointer> GetInstructions(std::uint64_t beat) const {
        const auto begin = beat_offsets_[beat];
        const auto end = beat_offsets_[beat + 1];
        return std::span<const InstructionPointer>(
                instruction_ptrs_.data() + begin,
                end - begin
        );
    }
    const TimeSeries::ChipInfo& GetChipInfo(std::uint64_t beat) const {
        return beat2chip_[beat];
    }
    std::size_t InstructionBucketCount() const {
        return GetRuntime();
    }
    std::size_t InstructionBucketCapacity() const {
        return beat_offsets_.capacity() == 0 ? 0 : beat_offsets_.capacity() - 1;
    }
    std::size_t InstructionPointerCount() const {
        return instruction_ptrs_.size();
    }
    std::size_t InstructionPointerCapacity() const {
        return instruction_ptrs_.capacity();
    }
    std::size_t ChipInfoCount() const {
        return beat2chip_.size();
    }
    std::size_t ChipInfoCapacity() const {
        return beat2chip_.capacity();
    }
    std::size_t OffsetCount() const {
        return beat_offsets_.size();
    }
    std::size_t OffsetCapacity() const {
        return beat_offsets_.capacity();
    }

private:
    std::vector<std::size_t> beat_offsets_;
    std::vector<InstructionPointer> instruction_ptrs_;
    std::vector<TimeSeries::ChipInfo> beat2chip_;
};

struct QRET_EXPORT SummaryBeatMetrics {
    std::vector<const ScLsInstructionBase*> instructions;
    TimeSeries::ChipInfo chip_info = {};
    std::uint64_t gate_throughput = 0;
    std::uint64_t measurement_feedback_rate = 0;
    std::uint64_t magic_state_consumption_rate = 0;
    std::uint64_t entanglement_consumption_rate = 0;
};

QRET_EXPORT std::vector<SummaryBeatMetrics>
CollectLegacyTimeSeriesBeatMetrics(const MachineFunction& mf);
QRET_EXPORT std::vector<SummaryBeatMetrics>
CollectCompactTimeSeriesBeatMetrics(const MachineFunction& mf);
QRET_EXPORT std::vector<SummaryBeatMetrics> CollectEventSweepBeatMetrics(const MachineFunction& mf);
QRET_EXPORT ScLsFixedV0CompileInfo CalculateEventSweepSummaryForTest(const MachineFunction& mf);
/**
 * @brief Calculate compile information without topology.
 * @details Calculate following statistics:
 *
 * * about runtime
 *     * runtime_without_topology
 * * about gate
 *     * gate_count
 *     * gate_count_dict
 *     * gate_depth
 * * about measurement
 *     * measurement_feedback_count
 *     * measurement_feedback_depth
 *     * runtime_estimation_measurement_feedback_count
 *     * runtime_estimation_measurement_feedback_depth
 * * about magic state
 *     * magic_state_consumption_count
 *     * magic_state_consumption_depth
 *     * runtime_estimation_magic_state_consumption_count
 *     * runtime_estimation_magic_state_consumption_depth
 *     * magic_factory_count
 * * about entanglement
 *     * entanglement_consumption_count
 *     * entanglement_consumption_depth
 *     * runtime_estimation_entanglement_consumption_count
 *     * runtime_estimation_entanglement_consumption_depth
 *     * entanglement_factory_count
 */
struct QRET_EXPORT CompileInfoWithoutTopology : public MachineFunctionPass {
    static inline char ID = 0;
    CompileInfoWithoutTopology()
        : MachineFunctionPass(&ID) {}

    bool RunOnMachineFunction(MachineFunction& mf) override;
};
/**
 * @brief Calculate compile information with topology.
 * @details Calculate following statistics:
 *
 * * about runtime
 *     * runtime
 * * about gate
 *     * gate_throughput
 * * about measurement
 *     * measurement_feedback_rate
 * * about magic state
 *     * magic_state_consumption_rate
 * * about entanglement
 *     * entanglement_consumption_rate
 * * about cell consumption
 *     * chip_cell_count
 *     * chip_cell_algorithmic_qubit
 *     * chip_cell_algorithmic_qubit_ratio
 *     * chip_cell_activate_qubit_area
 *     * chip_cell_activate_qubit_area_ratio
 *     * qubit_volume
 */
struct QRET_EXPORT CompileInfoWithTopology : public MachineFunctionPass {
    static inline char ID = 0;
    CompileInfoWithTopology()
        : MachineFunctionPass(&ID) {}

    bool RunOnMachineFunction(MachineFunction& mf) override;
};
/**
 * @brief Estimate QEC-related compile information.
 * @details Run CompileInfoWithTopology and CompileInfoWithoutTopology passes before running this
 * pass. This pass adds the following statistics:
 *
 * * code_distance
 * * execution_time_sec
 * * num_physical_qubits
 */
struct QRET_EXPORT CompileInfoWithQecResourceEstimation : public MachineFunctionPass {
    static inline char ID = 0;
    CompileInfoWithQecResourceEstimation()
        : MachineFunctionPass(&ID) {}

    /**
     * @brief Estimate the minimum odd code distance that satisfies the target failure probability.
     * @details Uses pL = p * lambda^{(d-1)/2} and requires pL * active_volume <= eps.
     *
     * @param p Physical error rate.
     * @param lambda Drop rate in (0, 1).
     * @param eps Allowed failure probability for the program.
     * @param active_volume Active volume (e.g., sum of active qubits over code beats).
     */
    static std::uint64_t
    EstimateMinimumCodeDistance(double p, double lambda, double eps, std::uint64_t active_volume);
    /**
     * @brief Estimate execution time in seconds.
     * @details execution_time_sec = runtime * d * t_cycle.
     *
     * @param d Code distance.
     * @param runtime Number of code beats.
     * @param t_cycle Code cycle time in seconds.
     */
    static double EstimateExecutionTimeSec(std::uint64_t d, std::uint64_t runtime, double t_cycle);
    /**
     * @brief Estimate number of physical qubits.
     * @details num_physical_qubits = chip_cell_count * d^2 * 2.
     *
     * @param d Code distance.
     * @param chip_cell_count Number of cells in the chip.
     */
    static std::uint64_t EstimatePhysicalQubitCount(std::uint64_t d, std::uint64_t chip_cell_count);

    bool RunOnMachineFunction(MachineFunction& mf) override;
};
/**
 * @brief Initialize compile information.
 */
struct QRET_EXPORT InitCompileInfo : public MachineFunctionPass {
    static inline char ID = 0;
    InitCompileInfo()
        : MachineFunctionPass(&ID) {}

    bool RunOnMachineFunction(MachineFunction& mf) override;
};
/**
 * @brief Dump compile information.
 */
struct QRET_EXPORT DumpCompileInfo : public MachineFunctionPass {
    static inline char ID = 0;
    DumpCompileInfo()
        : MachineFunctionPass(&ID) {}

    bool RunOnMachineFunction(MachineFunction& mf) override;
};
}  // namespace qret::sc_ls_fixed_v0

#endif  // QRET_TARGET_SC_LS_FIXED_V0_CALC_COMPILE_INFO_H
