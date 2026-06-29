/**
 * @file qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_compile_backend.cpp
 * @brief Compile backend for SC_LS_FIXED_V0 target.
 */

#include "qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_compile_backend.h"

#include <fmt/format.h>

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string_view>
#include <vector>

#include "qret/base/log.h"
#include "qret/base/rss_profile.h"
#include "qret/base/string.h"
#include "qret/codegen/machine_function.h"
#include "qret/codegen/machine_function_pass.h"
#include "qret/frontend/builder.h"
#include "qret/frontend/openqasm2.h"
#include "qret/ir/context.h"
#include "qret/ir/function.h"
#include "qret/ir/json.h"
#include "qret/ir/module.h"
#include "qret/parser/openqasm2.h"
#include "qret/pass.h"
#include "qret/target/sc_ls_fixed_v0/external_pass.h"
#include "qret/target/sc_ls_fixed_v0/lowering.h"
#include "qret/target/sc_ls_fixed_v0/magic_path_profile.h"
#include "qret/target/sc_ls_fixed_v0/memory_profile_stats.h"
#include "qret/target/sc_ls_fixed_v0/pipeline_state.h"
#include "qret/target/sc_ls_fixed_v0/sc_ls_fixed_v0_target_machine.h"
#include "qret/target/sc_ls_fixed_v0/topology.h"
#include "qret/target/target_registry.h"
#include "qret/transforms/ipo/inliner.h"
#include "qret/transforms/scalar/decomposition.h"
#include "qret/transforms/scalar/ignore_global_phase.h"
#include "qret/transforms/scalar/static_condition_pruning.h"

namespace qret::sc_ls_fixed_v0 {
namespace {
qret::Json FunctionStats(const qret::ir::Function* func) {
    auto extra = qret::Json::object();
    if (func == nullptr) {
        extra["ir_function_present"] = false;
        return extra;
    }
    extra["ir_function_present"] = true;
    extra["ir_basic_blocks"] = func->GetNumBBs();
    extra["ir_instructions"] = func->GetInstructionCount();
    extra["ir_qubits"] = func->GetNumQubits();
    extra["ir_registers"] = func->GetNumRegisters();
    extra["ir_tmp_registers"] = func->GetNumTmpRegisters();
    return extra;
}

qret::Json MachineFunctionStats(const qret::MachineFunction& mf) {
    return qret::sc_ls_fixed_v0::MachineFunctionMemoryStats(mf);
}

qret::Json MachineFunctionStats(
        const qret::MachineFunction& mf,
        bool skip_pipeline_state_output
) {
    auto extra = MachineFunctionStats(mf);
    extra["skip_pipeline_state_output"] = skip_pipeline_state_output;
    return extra;
}

void MergeJson(qret::Json& dest, const qret::Json& source) {
    for (auto it = source.begin(); it != source.end(); ++it) {
        dest[it.key()] = it.value();
    }
}

// This backend depends only on CompileOptionReader, not on value sources.
std::vector<qret::PassConfig> GetDefaultPass(const CompileFormat source) {
    if (source == CompileFormat::SC_LS_FIXED_V0) {
        return {};
    }

    auto ret = std::vector<qret::PassConfig>();
    ret.emplace_back("sc_ls_fixed_v0::init_compile_info");
    if (source == CompileFormat::IR || source == CompileFormat::OPENQASM2) {
        ret.emplace_back("sc_ls_fixed_v0::mapping");
    }
    ret.emplace_back("sc_ls_fixed_v0::routing");
    ret.emplace_back("sc_ls_fixed_v0::calc_info_without_topology");
    ret.emplace_back("sc_ls_fixed_v0::calc_info_with_topology");
    ret.emplace_back("sc_ls_fixed_v0::dump_compile_info");
    return ret;
}

std::optional<qret::ir::Function*>
LoadFunctionFromIR(const qret::CompileRequest& request, qret::ir::IRContext& context) {
    LOG_INFO("Load IR.");
    auto input_extra = qret::Json::object();
    input_extra["input"] = request.input;
    input_extra["explicit_input_buffer_present"] = false;
    try {
        input_extra["ir_file_size_bytes"] = std::filesystem::file_size(request.input);
    } catch (...) {
        input_extra["ir_file_size_bytes"] = nullptr;
    }
    qret::rss_profile::Mark("before_input_json_read", input_extra);
    qret::rss_profile::Mark("before_ir_file_read", input_extra);
    auto ifs = std::ifstream(request.input);
    qret::rss_profile::Mark("after_input_json_read", input_extra);
    qret::rss_profile::Mark("after_ir_file_read", input_extra);
    qret::rss_profile::Mark("before_ir_json_parse", input_extra);
    auto j = qret::Json::parse(ifs);
    auto json_extra = qret::sc_ls_fixed_v0::JsonDomMemoryStats(j);
    json_extra["input"] = request.input;
    json_extra["explicit_input_buffer_present"] = false;
    json_extra["ir_file_size_bytes"] = input_extra["ir_file_size_bytes"];
    qret::rss_profile::Mark("after_json_parse_or_dom_build", json_extra);
    qret::rss_profile::Mark("after_ir_json_parse", json_extra);
    qret::rss_profile::Mark("load_ir_after_json_parse_json_alive", json_extra);

    LOG_INFO("Find function.");
    qret::rss_profile::Mark("before_load_json", json_extra);
    qret::ir::LoadJson(j, context);
    auto load_extra = qret::Json::object();
    load_extra["module_count"] = context.owned_module.size();
    MergeJson(load_extra, json_extra);
    qret::rss_profile::Mark("after_load_json_machine_function_built", load_extra);
    qret::rss_profile::Mark("load_ir_after_load_json_json_alive", load_extra);
    auto* func = context.owned_module.back()->GetFunction(request.function_name);
    if (func == nullptr) {
        std::cerr << "function of name '" << request.function_name << "' not found" << std::endl;
        return std::nullopt;
    }
    auto destroy_extra = FunctionStats(func);
    destroy_extra["json_dom_present"] = true;
    MergeJson(destroy_extra, json_extra);
    qret::rss_profile::Mark("before_ir_json_dom_destroy", destroy_extra);
    qret::rss_profile::Mark("load_ir_before_return_json_alive", destroy_extra);
    return func;
}

std::optional<qret::ir::Function*>
LoadFunctionFromOpenQASM2(const qret::CompileRequest& request, qret::ir::IRContext& context) {
    LOG_INFO("Load OpenQASM2.");
    const auto ast = qret::openqasm2::ParseOpenQASM2File(request.input);

    LOG_INFO("Build IR from OpenQASM2.");
    auto* module = qret::ir::Module::Create("OpenQASM2", context);
    auto builder = qret::frontend::CircuitBuilder(module);
    const auto entry_name = request.function_name.empty() ? "main" : request.function_name;
    auto* circuit = qret::frontend::BuildCircuitFromAST(ast, builder, entry_name);
    return circuit->GetIR();
}

std::optional<std::shared_ptr<qret::sc_ls_fixed_v0::Topology>> LoadTopology(
        const qret::CompileOptionReader& options
) {
    if (!options.Contains("sc_ls_fixed_v0_topology")) {
        std::cerr << "Topology is not specified." << std::endl;
        return std::nullopt;
    }
    const auto topology_path = options.GetString("sc_ls_fixed_v0_topology");
    auto topology_ifs = std::ifstream(topology_path);
    return topology_path.ends_with(".json")
            ? qret::sc_ls_fixed_v0::Topology::FromJSON(qret::Json::parse(topology_ifs))
            : qret::sc_ls_fixed_v0::Topology::FromYAML(qret::LoadFile(topology_path));
}

std::optional<qret::sc_ls_fixed_v0::ScLsFixedV0MachineOption> GetMachineOption(
        const qret::CompileOptionReader& options,
        const qret::sc_ls_fixed_v0::Topology& topology
) {
    const auto enable_pbc_mode = options.Contains("sc_ls_fixed_v0_enable_pbc_mode");
    const auto machine_type_str = options.GetString("sc_ls_fixed_v0_machine_type", "auto");
    const auto required_type = qret::sc_ls_fixed_v0::GetMachineType(topology);
    auto machine_type = required_type;
    if (machine_type_str != "auto") {
        try {
            machine_type = qret::sc_ls_fixed_v0::ScLsFixedV0MachineTypeFromString(machine_type_str);
        } catch (const std::exception&) {
            std::cerr << "Error: Invalid --sc_ls_fixed_v0_machine_type '" << machine_type_str
                      << "'. Valid values are 'auto', 'Dim2', 'Dim3', 'DistributedDim2', "
                         "'DistributedDim3'.\n";
            return std::nullopt;
        }
    }
    if (!qret::sc_ls_fixed_v0::IsCompatible(machine_type, required_type)) {
        std::cerr << "Error: The specified machine type '" << machine_type_str
                  << "' is not compatible with the topology's minimum requirement of '"
                  << qret::sc_ls_fixed_v0::ToString(required_type) << "'.\n"
                  << "Please use a machine type that is either identical to or more advanced than '"
                  << qret::sc_ls_fixed_v0::ToString(required_type) << "'.\n";
        return std::nullopt;
    }
    if (enable_pbc_mode && machine_type != qret::sc_ls_fixed_v0::ScLsFixedV0MachineType::Dim2) {
        std::cerr << "Error: --sc_ls_fixed_v0_enable_pbc_mode currently supports only "
                     "--sc_ls_fixed_v0_machine_type=Dim2.\n";
        return std::nullopt;
    }

    return qret::sc_ls_fixed_v0::ScLsFixedV0MachineOption{
            .type = machine_type,
            .enable_pbc_mode = enable_pbc_mode,
            .use_magic_state_cultivation =
                    options.Contains("sc_ls_fixed_v0_use_magic_state_cultivation"),
            .magic_factory_seed_offset =
                    options.GetUInt64("sc_ls_fixed_v0_magic_factory_seed_offset", 0),
            .magic_generation_period = options.GetUInt64("sc_ls_fixed_v0_magic_generation_period"),
            .prob_magic_state_creation =
                    options.GetDouble("sc_ls_fixed_v0_prob_magic_state_creation", 1.0),
            .maximum_magic_state_stock =
                    options.GetUInt64("sc_ls_fixed_v0_maximum_magic_state_stock"),
            .entanglement_generation_period =
                    options.GetUInt64("sc_ls_fixed_v0_entanglement_generation_period"),
            .maximum_entangled_state_stock =
                    options.GetUInt64("sc_ls_fixed_v0_maximum_entangled_state_stock"),
            .reaction_time = options.GetUInt64("sc_ls_fixed_v0_reaction_time"),
            .physical_error_rate = options.GetDouble("sc_ls_fixed_v0_physical_error_rate", 0.0),
            .drop_rate = options.GetDouble("sc_ls_fixed_v0_drop_rate", 0.0),
            .code_cycle_time_sec = options.GetDouble("sc_ls_fixed_v0_code_cycle_time_sec", 0.0),
            .allowed_failure_prob = options.GetDouble("sc_ls_fixed_v0_allowed_failure_prob", 0.0)
    };
}

bool RunCompilation(
        const qret::CompileRequest& request,
        const std::shared_ptr<qret::sc_ls_fixed_v0::Topology>& topology,
        const qret::sc_ls_fixed_v0::ScLsFixedV0MachineOption& option,
        const std::vector<qret::PassConfig>& pass_config,
        bool skip_pipeline_state_output
) {
    auto start_extra = qret::Json::object();
    start_extra["pass_count"] = pass_config.size();
    start_extra["source_format"] = static_cast<std::int32_t>(request.source_format);
    start_extra["skip_pipeline_state_output"] = skip_pipeline_state_output;
    qret::rss_profile::Mark("run_compilation_start", start_extra);
    auto target_machine = qret::sc_ls_fixed_v0::ScLsFixedV0TargetMachine::New(topology, option);

    auto mf = qret::MachineFunction(target_machine.get());
    auto manager = qret::MFPassManager();

    if (request.source_format == qret::CompileFormat::IR
        || request.source_format == qret::CompileFormat::OPENQASM2) {
        qret::ir::IRContext context;
        const auto func = request.source_format == qret::CompileFormat::IR
                ? LoadFunctionFromIR(request, context)
                : LoadFunctionFromOpenQASM2(request, context);
        if (!func.has_value()) {
            return false;
        }
        auto json_destroyed_extra = FunctionStats(*func);
        json_destroyed_extra["json_dom_present"] = false;
        json_destroyed_extra["explicit_input_buffer_present"] = false;
        qret::rss_profile::Mark("after_ir_json_dom_destroy", json_destroyed_extra);
        if (request.source_format == qret::CompileFormat::IR) {
            qret::rss_profile::MaybeDiagnosticTrim("after_json_dom_destroy");
        }
        auto buffer_extra = qret::Json::object();
        buffer_extra["explicit_input_buffer_present"] = false;
        buffer_extra["input_buffer_size"] = 0;
        buffer_extra["input_buffer_capacity"] = 0;
        qret::rss_profile::Mark("before_input_buffer_destroy", buffer_extra);
        qret::rss_profile::Mark("after_input_buffer_destroy", buffer_extra);
        qret::rss_profile::Mark("after_load_function_json_destroyed", FunctionStats(*func));
        mf.SetIR(*func);
        qret::rss_profile::Mark("after_set_ir", MachineFunctionStats(mf));

        LOG_INFO("Simplify IR before compiling to SC_LS_FIXED_V0.");
        qret::ir::RecursiveInlinerPass().RunOnFunction(**func);
        qret::rss_profile::Mark("after_recursive_inliner", FunctionStats(*func));
        qret::ir::StaticConditionPruningPass().RunOnFunction(**func);
        qret::rss_profile::Mark("after_static_condition_pruning", FunctionStats(*func));
        qret::ir::DecomposeInst().RunOnFunction(**func);
        qret::rss_profile::Mark("after_decompose_inst", FunctionStats(*func));
        qret::ir::IgnoreGlobalPhase().RunOnFunction(**func);
        qret::rss_profile::Mark("after_ignore_global_phase", FunctionStats(*func));

        LOG_INFO("Lowering IR to the machine function of SC_LS_FIXED_V0.");
        auto before_lowering_extra = MachineFunctionStats(mf);
        qret::rss_profile::Mark("before_machine_function_construction", before_lowering_extra);
        qret::rss_profile::Mark("before_lowering", before_lowering_extra);
        qret::sc_ls_fixed_v0::Lowering().RunOnMachineFunction(mf);
        auto after_lowering_extra = MachineFunctionStats(mf);
        qret::rss_profile::Mark("after_machine_function_construction", after_lowering_extra);
        qret::rss_profile::MaybeDiagnosticTrim("after_machine_function_construction");
        qret::rss_profile::Mark("after_lowering", after_lowering_extra);
    } else {
        LOG_INFO("Load SC_LS_FIXED_V0 pipeline state file.");
        auto state = qret::sc_ls_fixed_v0::LoadPipelineState(request.input);
        qret::sc_ls_fixed_v0::ApplyPipelineState(state, manager, target_machine, mf);
        qret::rss_profile::Mark("after_load_pipeline_state", MachineFunctionStats(mf));
    }
    qret::rss_profile::Mark("after_ir_context_scope", MachineFunctionStats(mf));

    LOG_INFO("Run passes.");
    const auto add_pass = [&manager](std::string_view arg) {
        const auto* registry = qret::PassRegistry::GetPassRegistry();
        if (!registry->Contains(arg)) {
            throw std::runtime_error(fmt::format("unknown pass: {}", arg));
        }
        auto* pass = manager.AddPass((registry->GetPassInfo(arg)->GetNormalCtor())());
        if (pass == nullptr) {
            throw std::runtime_error(fmt::format("Cannot use pass {} from command line.", arg));
        }
    };
    const auto add_external_pass = [&manager](const qret::PassConfig& config) {
        manager.AddPass(
                std::unique_ptr<qret::sc_ls_fixed_v0::ExternalPass>(
                        new qret::sc_ls_fixed_v0::ExternalPass(
                                config.arg,
                                config.cmd,
                                config.input,
                                config.output,
                                config.runner
                        )
                )
        );
    };
    for (const auto& config : pass_config) {
        if (config.IsExternalPass()) {
            add_external_pass(config);
        } else {
            add_pass(config.arg);
        }
    }
    qret::rss_profile::Mark("before_pass_manager_run", MachineFunctionStats(mf));
    manager.Run(mf);
    qret::rss_profile::Mark(
            "after_pass_manager_run",
            MachineFunctionStats(mf, skip_pipeline_state_output)
    );
    qret::sc_ls_fixed_v0::MaybeWriteLatticeSurgeryMagicPathProfile(
            mf,
            "after_pass_manager_run"
    );

    if (skip_pipeline_state_output) {
        LOG_INFO("Skip SC_LS_FIXED_V0 pipeline state output.");
        const auto extra = MachineFunctionStats(mf, skip_pipeline_state_output);
        qret::rss_profile::Mark("pipeline_state_output_skipped", extra);
        qret::rss_profile::Mark("run_compilation_end", extra);
        return true;
    }

    LOG_INFO("Save SC_LS_FIXED_V0 pipeline state file.");
    qret::rss_profile::Mark(
            "before_build_pipeline_state",
            MachineFunctionStats(mf, skip_pipeline_state_output)
    );
    const auto state = qret::sc_ls_fixed_v0::BuildPipelineState(manager, target_machine, mf);
    qret::rss_profile::Mark(
            "after_build_pipeline_state",
            MachineFunctionStats(mf, skip_pipeline_state_output)
    );
    qret::sc_ls_fixed_v0::SavePipelineState(request.output, state);
    const auto extra = MachineFunctionStats(mf, skip_pipeline_state_output);
    qret::rss_profile::Mark("after_save_pipeline_state", extra);
    qret::rss_profile::Mark("run_compilation_end", extra);
    return true;
}
}  // namespace

std::string_view ScLsFixedV0CompileBackend::TargetName() const {
    return "sc_ls_fixed_v0";
}

void ScLsFixedV0CompileBackend::AddCompileOptions(qret::CompileOptionRegistrar& registrar) const {
    registrar.AddStringOption(
            "sc_ls_fixed_v0_topology",
            "FILE",
            "Path to the SC_LS_FIXED_V0 topology file."
    );
    registrar.AddStringOptionWithDefault(
            "sc_ls_fixed_v0_machine_type",
            "auto",
            "TYPE",
            "SC_LS_FIXED_V0 machine type: 'Dim2', 'Dim3', 'DistributedDim2', or "
            "'DistributedDim3' (currently unsupported). "
            "When 'auto' (default), the type is inferred from --sc_ls_fixed_v0_topology as the "
            "minimum required."
    );
    registrar.AddFlagOption(
            "sc_ls_fixed_v0_enable_pbc_mode",
            "Enable Pauli Based Computing lowering mode."
    );
    registrar.AddFlagOption(
            "sc_ls_fixed_v0_use_magic_state_cultivation",
            "Simulate magic-state factories using the cultivation method "
            "(requires --sc_ls_fixed_v0_magic_factory_seed_offset, "
            "--sc_ls_fixed_v0_prob_magic_state_creation)."
    );
    registrar.AddFlagOption(
            "sc_ls_fixed_v0_skip_pipeline_state_output",
            "Skip writing the SC_LS_FIXED_V0 pipeline-state output file."
    );
    registrar.AddUInt64Option(
            "sc_ls_fixed_v0_magic_factory_seed_offset",
            0,
            "Base seed offset for RNG initialization of each magic-state factory. "
            "Required only if --sc_ls_fixed_v0_use_magic_state_cultivation=true."
    );
    registrar.AddUInt64Option(
            "sc_ls_fixed_v0_magic_generation_period",
            15,
            "Beats required to produce one magic state."
    );
    registrar.AddDoubleOption(
            "sc_ls_fixed_v0_prob_magic_state_creation",
            1.0,
            "Per-attempt success probability for magic-state creation. "
            "Required only if --sc_ls_fixed_v0_use_magic_state_cultivation=true."
    );
    registrar.AddUInt64Option(
            "sc_ls_fixed_v0_maximum_magic_state_stock",
            10000,
            "Maximum number of magic states storable in a factory."
    );
    registrar.AddUInt64Option(
            "sc_ls_fixed_v0_entanglement_generation_period",
            100,
            "Beats required to generate one entangled pair."
    );
    registrar.AddUInt64Option(
            "sc_ls_fixed_v0_maximum_entangled_state_stock",
            10,
            "Maximum number of entangled pairs storable in a factory."
    );
    registrar.AddUInt64Option(
            "sc_ls_fixed_v0_reaction_time",
            1,
            "Feed-forward latency in beats from measurement to error-corrected value."
    );
    registrar.AddDoubleOption(
            "sc_ls_fixed_v0_physical_error_rate",
            0.0,
            "Physical error rate p for logical error estimation."
    );
    registrar.AddDoubleOption(
            "sc_ls_fixed_v0_drop_rate",
            0.0,
            "Drop rate Lambda for logical error estimation."
    );
    registrar.AddDoubleOption(
            "sc_ls_fixed_v0_code_cycle_time_sec",
            0.0,
            "Code cycle time in seconds (t_cycle) for execution time estimation."
    );
    registrar.AddDoubleOption(
            "sc_ls_fixed_v0_allowed_failure_prob",
            0.0,
            "Allowed failure probability (eps) for logical error estimation."
    );
    registrar.AddStringOption(
            "sc_ls_fixed_v0_pass",
            "PASS",
            "SC_LS_FIXED_V0 compile pass to run. Accepts a single pass or a comma-separated "
            "list."
    );
}

bool ScLsFixedV0CompileBackend::Supports(const CompileFormat source) const {
    const auto source_supported = source == CompileFormat::IR || source == CompileFormat::OPENQASM2
            || source == CompileFormat::SC_LS_FIXED_V0;
    return source_supported;
}

bool ScLsFixedV0CompileBackend::Compile(
        const qret::CompileRequest& request,
        const qret::CompileOptionReader& options
) const {
    if (!Supports(request.source_format)) {
        std::cerr << "source format is not supported for target 'SC_LS_FIXED_V0'" << std::endl;
        return false;
    }
    if (request.source_format == qret::CompileFormat::IR && request.function_name.empty()) {
        std::cerr << "--function option is required" << std::endl;
        return false;
    }

    auto start_extra = qret::Json::object();
    start_extra["input"] = request.input;
    start_extra["output"] = request.output;
    start_extra["function"] = request.function_name;
    start_extra["source_format"] = static_cast<std::int32_t>(request.source_format);
    qret::rss_profile::Mark("process_start", start_extra);
    qret::rss_profile::Mark("compile_entry", start_extra);
    qret::rss_profile::Mark("compile_backend_start", start_extra);

    const auto topology = LoadTopology(options);
    qret::rss_profile::Mark("compile_backend_after_load_topology");
    if (!topology.has_value()) {
        auto exit_extra = start_extra;
        exit_extra["success"] = false;
        exit_extra["failure_stage"] = "load_topology";
        qret::rss_profile::Mark("compile_exit", exit_extra);
        return false;
    }
    const auto machine_option = GetMachineOption(options, *topology.value());
    qret::rss_profile::Mark("compile_backend_after_machine_option");
    if (!machine_option.has_value()) {
        auto exit_extra = start_extra;
        exit_extra["success"] = false;
        exit_extra["failure_stage"] = "machine_option";
        qret::rss_profile::Mark("compile_exit", exit_extra);
        return false;
    }
    const auto pass_config = options.Contains("sc_ls_fixed_v0_pass")
            ? options.GetPassConfigList("sc_ls_fixed_v0_pass")
            : GetDefaultPass(request.source_format);
    const auto skip_pipeline_state_output =
            options.Contains("sc_ls_fixed_v0_skip_pipeline_state_output");
    auto pass_extra = qret::Json::object();
    pass_extra["pass_count"] = pass_config.size();
    pass_extra["skip_pipeline_state_output"] = skip_pipeline_state_output;
    qret::rss_profile::Mark("compile_backend_after_pass_config", pass_extra);
    const auto success = RunCompilation(
            request,
            topology.value(),
            machine_option.value(),
            pass_config,
            skip_pipeline_state_output
    );
    auto exit_extra = pass_extra;
    exit_extra["success"] = success;
    qret::rss_profile::Mark("before_process_exit", exit_extra);
    qret::rss_profile::Mark("compile_exit", exit_extra);
    return success;
}
}  // namespace qret::sc_ls_fixed_v0
