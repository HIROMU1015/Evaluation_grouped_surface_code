#include "qret/target/sc_ls_fixed_v0/calc_compile_info.h"

#include <gtest/gtest.h>

#include <cstdlib>
#include <list>
#include <tuple>
#include <vector>

#include "qret/base/graph.h"
#include "qret/codegen/machine_function.h"
#include "qret/target/sc_ls_fixed_v0/geometry.h"
#include "qret/target/sc_ls_fixed_v0/instruction.h"
#include "qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_target_machine.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
using Edge = std::tuple<CompactDepGraph::IdType, CompactDepGraph::IdType, CompactDepGraph::Length>;

CompactDepGraph BuildCompact(
        const std::vector<CompactDepGraph::Weight>& weights,
        const std::vector<Edge>& edges
) {
    auto graph = CompactDepGraph();
    for (auto id = std::size_t{0}; id < weights.size(); ++id) {
        graph.AddNode(weights[id]);
        for (const auto& [from, to, length] : edges) {
            if (to == id) {
                graph.AddEdgeToCurrentNode(from, length);
            }
        }
    }
    graph.Finalize();
    return graph;
}

DiGraph BuildLegacy(
        const std::vector<CompactDepGraph::Weight>& weights,
        const std::vector<Edge>& edges
) {
    auto graph = DiGraph();
    for (auto id = std::size_t{0}; id < weights.size(); ++id) {
        graph.AddNode(static_cast<DiGraph::IdType>(id), weights[id]);
    }
    for (const auto& [from, to, length] : edges) {
        graph.AddEdge(from, to, length);
    }
    EXPECT_TRUE(graph.Topsort());
    return graph;
}

void ExpectMatchesLegacy(
        const std::vector<CompactDepGraph::Weight>& weights,
        const std::vector<Edge>& edges
) {
    auto compact = BuildCompact(weights, edges);
    auto legacy = BuildLegacy(weights, edges);
    const auto [legacy_weight, _legacy_path, _legacy_node_weights] = FindHeaviestPath(legacy);
    const auto [legacy_length, _legacy_longest_path, _legacy_node_lengths] =
            FindLongestPath(legacy);
    EXPECT_EQ(compact.NumNodes(), legacy.NumNodes());
    EXPECT_EQ(compact.NumEdges(), legacy.NumEdges());
    EXPECT_EQ(compact.CalcHeaviest(), legacy_weight);
    EXPECT_EQ(compact.CalcLongest(), legacy_length);
    EXPECT_TRUE(compact.TopologicalOrderInvariant());
}

struct DepGraphMetrics {
    std::size_t nodes = 0;
    std::size_t edges = 0;
    DepGraph::Weight gate_depth = 0;
    DepGraph::Weight magic_depth = 0;
    DepGraph::Weight entanglement_depth = 0;
    DepGraph::Length measurement_depth = 0;
};

DepGraphMetrics Measure(DepGraph& graph, const MachineFunction& mf) {
    auto ret = DepGraphMetrics{.nodes = graph.NumNodes(), .edges = graph.NumEdges()};

    auto id = DepGraph::IdType{0};
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            graph.SetNodeWeight(id, inst.Latency() == 0 ? 0 : 1);
            ++id;
        }
    }
    ret.gate_depth = graph.CalcHeaviest();

    id = DepGraph::IdType{0};
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            graph.SetNodeWeight(id, inst.UseMagicState() ? 1 : 0);
            ++id;
        }
    }
    ret.magic_depth = graph.CalcHeaviest();

    id = DepGraph::IdType{0};
    for (const auto& bb : mf) {
        for (const auto& minst : bb) {
            const auto& inst = *static_cast<const ScLsInstructionBase*>(minst.get());
            graph.SetNodeWeight(id, inst.UseEntanglement() ? 1 : 0);
            ++id;
        }
    }
    ret.entanglement_depth = graph.CalcHeaviest();

    graph.SetAllLength(0);
    graph.SetLength(4, 5, 1);
    ret.measurement_depth = graph.CalcLongest();
    return ret;
}

ScLsFixedV0TargetMachine& TestTarget() {
    static auto target = ScLsFixedV0TargetMachine();
    target.machine_option.reaction_time = 1;
    return target;
}

MachineFunction BuildMoveMachineFunction() {
    auto& target = TestTarget();
    auto mf = MachineFunction(&target);
    auto& bb = mf.AddBlock();
    bb.EmplaceBack(Allocate::New(QSymbol{0}, Coord3D{0, 0, 0}, 0, {}));
    bb.EmplaceBack(Move::New(QSymbol{0}, QSymbol{1}, {Coord3D{1, 0, 0}}, {}));
    bb.EmplaceBack(InitZX::New(QSymbol{1}, 0, {}));
    bb.EmplaceBack(MoveTrans::New(QSymbol{1}, QSymbol{2}, {}));
    bb.EmplaceBack(MeasZX::New(QSymbol{2}, MeasZX::Z, CSymbol{10}, {}));
    bb.EmplaceBack(InitZX::New(QSymbol{2}, 0, {CSymbol{10}}));
    return mf;
}
}  // namespace

TEST(CompactDepGraph, EmptyAndSingleNodeMatchLegacy) {
    ExpectMatchesLegacy({}, {});
    ExpectMatchesLegacy({7}, {});
}

TEST(CompactDepGraph, LinearForkJoinAndMultipleParentsMatchLegacy) {
    ExpectMatchesLegacy({1, 2, 3}, {{0, 1, 0}, {1, 2, 0}});
    ExpectMatchesLegacy({1, 2, 3, 4}, {{0, 1, 0}, {0, 2, 0}, {1, 3, 0}, {2, 3, 0}});
}

TEST(CompactDepGraph, DuplicateDependencyMatchesLegacyOverwriteSemantics) {
    auto compact = BuildCompact({1, 2}, {{0, 1, 3}, {0, 1, 5}});
    auto legacy = BuildLegacy({1, 2}, {{0, 1, 3}, {0, 1, 5}});
    const auto [legacy_length, _path, _node_lengths] = FindLongestPath(legacy);
    EXPECT_EQ(compact.NumEdges(), 1);
    EXPECT_EQ(compact.DuplicateEdgeCount(), 1);
    EXPECT_EQ(compact.CalcLongest(), legacy_length);
}

TEST(CompactDepGraph, ZeroWeightAndZeroLengthEdgesMatchLegacy) {
    ExpectMatchesLegacy({1, 0, 2}, {{0, 1, 0}, {1, 2, 0}});
    ExpectMatchesLegacy({1, 1, 1}, {{0, 2, 0}, {1, 2, 0}});
}

TEST(CompactDepGraph, WeightAndLengthUpdatesCoverMagicEntanglementAndFeedback) {
    auto graph = BuildCompact({0, 0, 0, 0}, {{0, 2, 0}, {1, 2, 0}, {2, 3, 0}});
    graph.SetNodeWeight(0, 1);
    graph.SetNodeWeight(1, 0);
    graph.SetNodeWeight(2, 1);
    graph.SetNodeWeight(3, 1);
    EXPECT_EQ(graph.CalcHeaviest(), 3);

    graph.SetAllLength(0);
    graph.SetLength(0, 2, 1);
    graph.SetLength(2, 3, 1);
    EXPECT_EQ(graph.CalcLongest(), 2);
}

TEST(CompactDepGraph, ReservedClassicalSymbolEquivalentHasNoEdge) {
    ExpectMatchesLegacy({1, 1}, {});
}

TEST(CompactDepGraph, InvalidNonTopologicalEdgeIsRejected) {
    auto graph = CompactDepGraph();
    graph.AddNode(1);
    EXPECT_THROW(graph.AddEdgeToCurrentNode(0), std::logic_error);
    graph.AddNode(1);
    EXPECT_THROW(graph.AddEdgeToCurrentNode(1), std::logic_error);
}

TEST(CompactDepGraph, MissingEdgeLengthUpdateIsRejected) {
    auto graph = BuildCompact({1, 1}, {});
    EXPECT_THROW(graph.SetLength(0, 1, 1), std::out_of_range);
}

TEST(DepGraph, LegacyAndCompactMatchForMoveAndMoveTransMachineFunction) {
    auto mf = BuildMoveMachineFunction();

    setenv("QRET_DEP_GRAPH_IMPL", "legacy", 1);
    auto legacy = DepGraph(mf);
    auto legacy_metrics = Measure(legacy, mf);

    setenv("QRET_DEP_GRAPH_IMPL", "compact", 1);
    auto compact = DepGraph(mf);
    auto compact_metrics = Measure(compact, mf);

    unsetenv("QRET_DEP_GRAPH_IMPL");
    EXPECT_EQ(compact_metrics.nodes, legacy_metrics.nodes);
    EXPECT_EQ(compact_metrics.edges, legacy_metrics.edges);
    EXPECT_EQ(compact_metrics.gate_depth, legacy_metrics.gate_depth);
    EXPECT_EQ(compact_metrics.magic_depth, legacy_metrics.magic_depth);
    EXPECT_EQ(compact_metrics.entanglement_depth, legacy_metrics.entanglement_depth);
    EXPECT_EQ(compact_metrics.measurement_depth, legacy_metrics.measurement_depth);
}
}  // namespace qret::sc_ls_fixed_v0
