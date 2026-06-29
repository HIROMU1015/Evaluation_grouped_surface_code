/**
 * @file qret/target/sc_ls_fixed_v0/routing.cpp
 * @brief Routing.
 */

#include "qret/target/sc_ls_fixed_v0/routing.h"

#include <fmt/format.h>

#include <cassert>
#include <cstdlib>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>

#include "qret/base/log.h"
#include "qret/base/option.h"
#include "qret/base/rss_profile.h"
#include "qret/codegen/inverse_map_profile.h"
#include "qret/codegen/machine_function.h"
#include "qret/pass.h"
#include "qret/target/sc_ls_fixed_v0/inst_queue.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
#include "qret/target/sc_ls_fixed_v0/magic_path_storage.h"
#include "qret/target/sc_ls_fixed_v0/memory_profile_stats.h"
#include "qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_target_machine.h"
#include "qret/target/sc_ls_fixed_v0/search_chip_comm.h"
#include "qret/target/sc_ls_fixed_v0/simulator.h"
#include "qret/target/sc_ls_fixed_v0/symbol.h"
#include "qret/target/sc_ls_fixed_v0/validation.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
static auto X = RegisterPass<Routing>("Routing", "sc_ls_fixed_v0::routing");

static Opt<std::int32_t> InstQueueWeightAlgorithm(
        "sc_ls_fixed_v0-inst-queue-weight-algorithm",
        2,
        "Weight algorithm of instruction queue (0: index, 1: type, 2: InvDepth)",
        OptionHidden::Hidden
);
static Opt<Beat> InstQueuePeekSize(
        "sc_ls_fixed_v0-inst-queue-peek-size",
        1000,
        "Peek size of instruction queue",
        OptionHidden::Hidden
);
static Opt<Beat> StateBufferWidth(
        "sc_ls_fixed_v0-state-buffer-width",
        20,
        "Buffer width of quantum states",
        OptionHidden::Hidden
);
static Opt<std::int32_t> RouteSearcherType(
        "sc_ls_fixed_v0-route-searcher-type",
        0,
        "Route searcher strategy (0: default)",
        OptionHidden::Hidden
);

enum class InverseMapConstructionMode {
    Eager,
    Lazy,
};

std::string ToString(InverseMapConstructionMode mode) {
    switch (mode) {
        case InverseMapConstructionMode::Eager:
            return "eager";
        case InverseMapConstructionMode::Lazy:
            return "lazy";
        default:
            return "unknown";
    }
}

qret::Json MachineFunctionStats(const MachineFunction& mf) {
    return RoutingLiveMemoryStats(mf);
}

qret::Json QueueStats(
        const MachineFunction& mf,
        const InstQueue& queue,
        const ScLsSimulator* simulator = nullptr
) {
    auto extra = RoutingLiveMemoryStats(mf, &queue, simulator);
    extra["queue_insts"] = queue.NumInsts();
    extra["queue_runnables"] = queue.NumRunnables();
    extra["queue_reserved"] = queue.NumReserved();
    extra["queue_peek_finished"] = queue.IsPeekFinished();
    return extra;
}

bool ReleaseInverseMapAfterRouting() {
    const auto* raw = std::getenv("QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING");
    if (raw == nullptr || std::string(raw).empty()) {
        return true;
    }
    const auto value = std::string(raw);
    if (value == "0") {
        return false;
    }
    if (value == "1") {
        return true;
    }
    throw std::invalid_argument("QRET_RELEASE_INVERSE_MAP_AFTER_ROUTING must be 0 or 1");
}

InverseMapConstructionMode ParseInverseMapConstructionMode() {
    const auto* raw = std::getenv("QRET_INVERSE_MAP_CONSTRUCTION");
    if (raw == nullptr || std::string(raw).empty() || std::string(raw) == "eager") {
        return InverseMapConstructionMode::Eager;
    }
    if (std::string(raw) == "lazy") {
        return InverseMapConstructionMode::Lazy;
    }
    throw std::invalid_argument("QRET_INVERSE_MAP_CONSTRUCTION must be eager or lazy");
}
}  // namespace

bool SkipAllocate(
        const std::int64_t initial_weight,
        const std::int64_t allocate_weight,
        InstQueue::WeightAlgorithm algorithm
) {
    if (algorithm != InstQueue::WeightAlgorithm::InvDepth) {
        return false;
    }

    assert(algorithm == InstQueue::WeightAlgorithm::InvDepth);
    // Skip if the weight of allocate instruction is too large.
    // return initial_weight + static_cast<std::int64_t>(StateBufferWidth) < allocate_weight;
    return initial_weight + 1 < allocate_weight;
}
bool Routing::RunOnMachineFunction(MachineFunction& mf) {
    qret::rss_profile::Mark("routing_entry", MachineFunctionStats(mf));
    if (InstQueueWeightAlgorithm > 2) {
        throw std::runtime_error(
                "InstQueueWeightAlgorithm must be 0, 1, or 2 (0: index, 1: type, 2: InvDepth)."
        );
    }
    if (InstQueuePeekSize <= 1) {
        throw std::runtime_error("InstQueuePeekSize must be larger than 1.");
    }
    if (StateBufferWidth <= 5) {
        throw std::runtime_error("StateBufferWidth must be larger than 5.");
    }
    if (RouteSearcherType != 0) {
        throw std::runtime_error("RouteSearcherType must be 0 (default).");
    }

    const auto& machine = *static_cast<const ScLsFixedV0TargetMachine*>(mf.GetTarget());
    const auto machine_type = machine.machine_option.type;
    const auto& topology = machine.topology;
    const auto& option = machine.machine_option;
    const auto weight_algorithm = InstQueue::WeightAlgorithm(InstQueueWeightAlgorithm.Get());

    if (machine_type == ScLsFixedV0MachineType::DistributedDim3) {
        throw std::runtime_error(
                "SC_LS_FIXED_V0 machine type DistributedDim3 is currently not supported."
        );
    }
    if (GetMachineType(*topology) == ScLsFixedV0MachineType::DistributedDim3) {
        LOG_ERROR("topology: {}", Json(*topology).dump());
        throw std::runtime_error(
                "SC_LS_FIXED_V0 machine type DistributedDim3 is currently not supported."
        );
    }

    Validate(mf);
    qret::rss_profile::Mark("routing_after_validate", MachineFunctionStats(mf));

    const auto inverse_map_construction_mode = ParseInverseMapConstructionMode();
    qret::inverse_map_profile::RecordBlockUniverse(mf);

    auto magic_path_interner = MagicPathInterner();
    auto magic_path_interning_scope = MagicPathInterningScope(magic_path_interner);

    if (inverse_map_construction_mode == InverseMapConstructionMode::Eager) {
        const auto inverse_map_stage =
                qret::inverse_map_profile::StageScope("routing_setup_construct_inverse_map");
        for (auto&& mbb : mf) {
            mbb.ConstructInverseMap();
        }
    }
    auto inverse_map_extra = MachineFunctionStats(mf);
    inverse_map_extra["inverse_map_construction_mode"] =
            ToString(inverse_map_construction_mode);
    qret::rss_profile::Mark("routing_after_construct_inverse_map", inverse_map_extra);

    auto changed = true;
    {
        auto symbol_generator = SymbolGenerator::New();
        {
            auto q_max = QSymbol::IdType{0};
            auto c_max = CSymbol::IdType{0};
            for (const auto& mbb : mf) {
                for (const auto& minst : mbb) {
                    const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
                    for (const auto q : inst.QTarget()) {
                        q_max = std::max(q_max, q.Id());
                    }
                    for (const auto c : inst.CCreate()) {
                        c_max = std::max(c_max, c.Id());
                    }
                }
            }
            symbol_generator->SetQ(QSymbol{q_max + 1});
            symbol_generator->SetC(CSymbol{c_max + 1});
        }
        qret::rss_profile::Mark("routing_after_symbol_generator", MachineFunctionStats(mf));
        auto splitter = SplitMultinodeInst(*topology, symbol_generator);
        qret::rss_profile::Mark("routing_after_splitter_construct", MachineFunctionStats(mf));

        // Define states.
        auto queue = InstQueue(option, mf, weight_algorithm);
        qret::rss_profile::Mark("routing_after_inst_queue_construct", QueueStats(mf, queue));
        qret::rss_profile::Mark("routing_after_queue_construct", QueueStats(mf, queue));
        auto route_searcher = std::unique_ptr<RouteSearcher>();
        if (RouteSearcherType == 0) {
            // Keep the simulator wired to the strategy interface, even with a single backend today.
            route_searcher = std::make_unique<DefaultRouteSearcher>();
        }
        qret::rss_profile::Mark("routing_after_route_searcher_construct", QueueStats(mf, queue));
        auto simulator = ScLsSimulator(
                *topology,
                option,
                StateBufferWidth,
                symbol_generator,
                std::move(route_searcher)
        );
        qret::rss_profile::Mark("routing_after_simulator_construct", QueueStats(mf, queue, &simulator));
        qret::rss_profile::Mark("routing_after_state_construct", QueueStats(mf, queue, &simulator));
        auto lightest_weight_of_inst_at_beat = std::numeric_limits<std::int64_t>::max();
        auto current_beat = simulator.GetBeat();
        auto idle_beats = Beat{0};

        // Peek instructions.
        queue.Peek(2 * InstQueuePeekSize);
        qret::rss_profile::Mark("routing_after_initial_queue_peek", QueueStats(mf, queue, &simulator));
        qret::rss_profile::Mark("routing_after_initial_peek", QueueStats(mf, queue, &simulator));
        if (!queue.Empty() && queue.NumRunnables() > 0) {
            lightest_weight_of_inst_at_beat = queue.GetNode(*queue.begin()).weight;
        }
        qret::rss_profile::Mark("routing_before_main_loop", QueueStats(mf, queue, &simulator));

        auto loop_iterations = std::uint64_t{0};
        {
            const auto inverse_map_stage =
                    qret::inverse_map_profile::StageScope("routing_main_loop");
            while (!queue.Empty()) {
                ++loop_iterations;
                if (qret::rss_profile::Enabled()
                    && (loop_iterations == 1 || loop_iterations % 32768 == 0)) {
                    auto peak_extra = QueueStats(mf, queue, &simulator);
                    peak_extra["routing_loop_iterations"] = loop_iterations;
                    peak_extra["routing_current_beat"] = current_beat;
                    qret::rss_profile::Mark("routing_main_loop_peak", peak_extra);
                }

                // DEBUG.
                if (queue.NumRunnables() == 0 && queue.NumReserved() == 0) {
                    throw std::logic_error(
                            "No runnable or reserved instructions in queue, while queue is not empty."
                    );
                }

                // Peek instructions if needed.
                if (!queue.IsPeekFinished() && queue.NumInsts() < InstQueuePeekSize) {
                    LOG_DEBUG("Peek instruction at beat: {}", current_beat);
                    queue.Peek(InstQueuePeekSize);
                }

                lightest_weight_of_inst_at_beat = queue.NumRunnables() == 0
                        ? std::numeric_limits<std::int64_t>::max()
                        : queue.GetNode(*queue.begin()).weight;

                // Run an instruction.
                auto update_inst_queue = false;
                auto success = false;
                for (auto* inst : queue) {
                    // The allocate instruction delays its execution as much as possible.
                    const auto type = inst->Type();
                    if (type == ScLsInstructionType::ALLOCATE
                        && SkipAllocate(
                                lightest_weight_of_inst_at_beat,
                                queue.GetNode(inst).weight,
                                weight_algorithm
                        )) {
                        continue;
                    }
                    if (machine_type == ScLsFixedV0MachineType::DistributedDim2
                        && (type == ScLsInstructionType::LATTICE_SURGERY_MULTINODE
                            || type == ScLsInstructionType::MOVE
                            || type == ScLsInstructionType::CNOT)
                        && splitter.Split(
                                simulator.GetStateBuffer().GetQuantumState(current_beat),
                                mf,
                                queue,
                                inst
                        )) {
                        // Rebuild queue dependencies first; runnability checks below should see the
                        // split form.
                        update_inst_queue = true;
                        break;
                    }

                    // Check if 'inst' is runnable.
                    if (simulator.Run(current_beat, queue, mf, inst)) {
                        success = true;
                        idle_beats = 0;
                        LOG_DEBUG("[BEAT {}] Run", current_beat);
                        break;
                    }
                }

                // If no instructions are runnable, step beat.
                if (!update_inst_queue && !success) {
                    ++current_beat;
                    ++idle_beats;
                    if (queue.SetBeat(current_beat) > 0) {
                        idle_beats = 0;
                    }
                    if (simulator.GetBeat() + StateBufferWidth / 2 < current_beat) {
                        simulator.StepBeat();
                    }
                    lightest_weight_of_inst_at_beat = queue.NumRunnables() == 0
                            ? std::numeric_limits<std::int64_t>::max()
                            : queue.GetNode(*queue.begin()).weight;
                }

                // Throw error if some instruction is not runnable for a long beats.
                if (idle_beats >= AllowedMaxIdleBeats(option)) {
                    auto ss = std::stringstream();
                    ss << "Do not process any instructions for " << idle_beats << " beats\n";
                    ss << "Routing pass failed to satisfy the following instructions:\n";
                    for (const auto* inst : queue) {
                        ss << "  * " << inst->ToString() << "\n";
                    }
                    throw std::runtime_error(ss.str());
                }
            }
        }

        LOG_DEBUG("Simulator stats: {}", simulator.GetStats());

        qret::rss_profile::Mark("routing_main_loop_exit", QueueStats(mf, queue, &simulator));
        qret::rss_profile::Mark("routing_after_main_loop", MachineFunctionStats(mf));
        qret::rss_profile::Mark("routing_before_temporary_destroy", QueueStats(mf, queue, &simulator));
    }
    qret::rss_profile::Mark("routing_after_temporary_destroy", MachineFunctionStats(mf));
    qret::rss_profile::MaybeDiagnosticTrim("after_routing_temporary_destroy");
    qret::rss_profile::Mark("routing_before_inverse_map_release", MachineFunctionStats(mf));
    if (ReleaseInverseMapAfterRouting()) {
        const auto inverse_map_stage =
                qret::inverse_map_profile::StageScope("routing_release_inverse_map");
        mf.ReleaseInverseMaps();
    }
    qret::rss_profile::Mark("routing_after_inverse_map_release", MachineFunctionStats(mf));
    qret::rss_profile::Mark("routing_pass_exit", MachineFunctionStats(mf));
    return changed;
}
}  // namespace qret::sc_ls_fixed_v0
