/**
 * @file qret/codegen/machine_function_pass.cpp
 * @brief Pass for MachineFunctions.
 */

#include "qret/codegen/machine_function_pass.h"

#include <chrono>  // NOLINT
#include <string>

#include "qret/base/log.h"
#include "qret/base/rss_profile.h"
#include "qret/codegen/machine_function.h"

namespace qret {
namespace {
std::size_t CountMachineInstructions(const MachineFunction& mf) {
    auto ret = std::size_t{0};
    for (const auto& mbb : mf) {
        ret += mbb.NumInstructions();
    }
    return ret;
}

qret::Json PassExtra(
        const MachineFunction& mf,
        const MachineFunctionPass& pass,
        std::size_t pass_index
) {
    auto extra = qret::Json::object();
    extra["pass_index"] = pass_index;
    extra["pass_name"] = std::string(pass.GetPassName());
    extra["pass_argument"] = std::string(pass.GetPassArgument());
    extra["machine_basic_blocks"] = mf.NumBBs();
    extra["machine_instructions"] = CountMachineInstructions(mf);
    extra["has_ir"] = mf.HasIR();
    extra["has_compile_info"] = mf.HasCompileInfo();
    return extra;
}

std::string_view BoundaryStage(std::string_view pass_argument, bool before) {
    if (pass_argument == "sc_ls_fixed_v0::mapping") {
        return before ? "before_mapping" : "after_mapping";
    }
    if (pass_argument == "sc_ls_fixed_v0::routing") {
        return before ? "routing_entry_from_pass_manager" : "routing_pass_exit";
    }
    if (pass_argument == "sc_ls_fixed_v0::calc_info_without_topology") {
        return before ? "before_calc_info_without_topology" : "after_calc_info_without_topology";
    }
    if (pass_argument == "sc_ls_fixed_v0::calc_info_with_topology") {
        return before ? "before_calc_info_with_topology" : "after_calc_info_with_topology";
    }
    return "";
}
}  // namespace

void MFPassManager::Run(MachineFunction& mf) {
    for (auto i = analysis_.run_order.size(); i < passes_.size(); ++i) {
        auto& pass = passes_[i];
        const auto start = std::chrono::high_resolution_clock::now();

        auto* ptr = static_cast<MachineFunctionPass*>(pass.get());
        LOG_INFO("Run {}", std::string(ptr->GetPassName()));
        auto before_extra = PassExtra(mf, *ptr, i);
        qret::rss_profile::Mark("mf_pass_before", before_extra);
        if (const auto boundary = BoundaryStage(ptr->GetPassArgument(), true); !boundary.empty()) {
            qret::rss_profile::Mark(boundary, before_extra);
        }
        if (ptr->GetPassArgument() == "sc_ls_fixed_v0::calc_info_without_topology") {
            qret::rss_profile::Mark("before_compile_info", before_extra);
        }
        ptr->RunOnMachineFunction(mf);

        const auto finish = std::chrono::high_resolution_clock::now();
        const auto elapsed_ms = std::chrono::duration_cast<MFAnalysis::Time>(finish - start);
        analysis_.run_order.emplace_back(ptr);
        analysis_.elapsed_ms[ptr] = elapsed_ms;
        auto extra = PassExtra(mf, *ptr, i);
        extra["elapsed_ms"] = elapsed_ms.count();
        if (const auto boundary = BoundaryStage(ptr->GetPassArgument(), false); !boundary.empty()) {
            qret::rss_profile::Mark(boundary, extra);
        }
        if (ptr->GetPassArgument() == "sc_ls_fixed_v0::mapping") {
            qret::rss_profile::MaybeDiagnosticTrim("after_mapping");
        }
        if (ptr->GetPassArgument() == "sc_ls_fixed_v0::calc_info_with_topology") {
            qret::rss_profile::Mark("after_compile_info", extra);
            qret::rss_profile::MaybeDiagnosticTrim("after_compile_info");
        }
        qret::rss_profile::Mark("mf_pass_after", extra);
    }
}
}  // namespace qret
