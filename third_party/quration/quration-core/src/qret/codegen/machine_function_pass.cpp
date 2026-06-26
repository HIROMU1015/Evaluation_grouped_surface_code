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
}  // namespace

void MFPassManager::Run(MachineFunction& mf) {
    for (auto i = analysis_.run_order.size(); i < passes_.size(); ++i) {
        auto& pass = passes_[i];
        const auto start = std::chrono::high_resolution_clock::now();

        auto* ptr = static_cast<MachineFunctionPass*>(pass.get());
        LOG_INFO("Run {}", std::string(ptr->GetPassName()));
        qret::rss_profile::Mark("mf_pass_before", PassExtra(mf, *ptr, i));
        ptr->RunOnMachineFunction(mf);

        const auto finish = std::chrono::high_resolution_clock::now();
        const auto elapsed_ms = std::chrono::duration_cast<MFAnalysis::Time>(finish - start);
        analysis_.run_order.emplace_back(ptr);
        analysis_.elapsed_ms[ptr] = elapsed_ms;
        auto extra = PassExtra(mf, *ptr, i);
        extra["elapsed_ms"] = elapsed_ms.count();
        qret::rss_profile::Mark("mf_pass_after", extra);
    }
}
}  // namespace qret
