/**
 * @file qret/cmd/opt.cpp
 * @brief Define 'opt' sumcommand in qret.
 */

#include "qret/cmd/opt.h"

#include <boost/program_options.hpp>
#include <fmt/format.h>

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <set>
#include <vector>

#include "qret/base/json.h"
#include "qret/base/log.h"
#include "qret/base/option.h"
#include "qret/cmd/common.h"
#include "qret/ir/context.h"
#include "qret/ir/function.h"
#include "qret/ir/function_pass.h"
#include "qret/ir/json.h"
#include "qret/ir/module.h"
#include "qret/pass.h"
#include "qret/transforms/external/external_pass.h"

namespace qret::cmd {
namespace {
std::vector<std::string> GetFunctionNames(const qret::ir::Module& module) {
    auto names = std::vector<std::string>{};
    for (const auto& function : module) {
        names.emplace_back(function.GetName());
    }
    std::sort(names.begin(), names.end());
    return names;
}

void PrintFunctionNotFound(const std::string& function_name, const qret::ir::Module& module) {
    std::cerr << "function of name '" << function_name << "' not found" << std::endl;
    std::cerr << "available functions:" << std::endl;
    for (const auto& name : GetFunctionNames(module)) {
        std::cerr << "  - " << name << std::endl;
    }
}

std::vector<qret::ir::Function*> ResolveFunctions(
        qret::ir::Module& module,
        const std::vector<std::string>& function_names
) {
    auto functions = std::vector<qret::ir::Function*>{};
    functions.reserve(function_names.size());
    for (const auto& function_name : function_names) {
        auto* func = module.GetFunction(function_name);
        if (func == nullptr) {
            PrintFunctionNotFound(function_name, module);
            return {};
        }
        functions.emplace_back(func);
    }
    return functions;
}

ReturnStatus RunPassesOnFunction(
        qret::ir::Function& func,
        const std::vector<PassConfig>& pass_config
) {
    for (const auto& config : pass_config) {
        const auto* registry = qret::PassRegistry::GetPassRegistry();

        if (config.IsExternalPass()) {
            auto pass = qret::ir::ExternalPass(
                    config.arg,
                    config.cmd,
                    config.input,
                    config.output,
                    config.runner
            );
            pass.RunOnFunction(func);
        } else {
            if (!registry->Contains(config.arg)) {
                throw std::runtime_error(fmt::format("unknown pass: {}", config.arg));
            }
            auto pass = (registry->GetPassInfo(config.arg)->GetNormalCtor())();
            if (pass == nullptr) {
                throw std::runtime_error(
                        fmt::format("Cannot use pass {} from command line.", config.arg)
                );
            }
            static_cast<ir::FunctionPass*>(pass.get())->RunOnFunction(func);
        }
    }
    return ReturnStatus::Success;
}

std::filesystem::path MakeTempOutputPath(const std::filesystem::path& output) {
    const auto parent = output.parent_path();
    const auto filename = output.filename().string();
    const auto tick = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto tmp_name = fmt::format(".{}.tmp.{}", filename, tick);
    if (parent.empty()) {
        return std::filesystem::path(tmp_name);
    }
    return parent / tmp_name;
}

ReturnStatus WriteModuleJsonAtomically(const qret::ir::Module& module, const std::string& output) {
    const auto output_path = std::filesystem::path(output);
    const auto tmp_path = MakeTempOutputPath(output_path);

    auto ofs = std::ofstream(tmp_path);
    if (!ofs.good()) {
        std::cerr << "failed to open: " << tmp_path << std::endl;
        return ReturnStatus::Failure;
    }
    ofs << Json(module);
    ofs.close();
    if (!ofs.good()) {
        std::cerr << "failed to write: " << tmp_path << std::endl;
        std::filesystem::remove(tmp_path);
        return ReturnStatus::Failure;
    }

    std::filesystem::rename(tmp_path, output_path);
    return ReturnStatus::Success;
}

std::optional<std::vector<std::string>> ParseOptFunctionNames(const VariablesMap& vm) {
    const auto has_functions = vm.yaml.has_value() && vm.yaml.value()["functions"].IsDefined();
    const auto has_function = vm.Contains("function");
    if (has_functions && has_function) {
        std::cerr << "function and functions are mutually exclusive" << std::endl;
        return std::nullopt;
    }
    if (has_functions) {
        const auto& functions_node = vm.yaml.value()["functions"];
        if (!functions_node.IsSequence() || functions_node.size() == 0) {
            std::cerr << "functions field must be a non-empty sequence" << std::endl;
            return std::nullopt;
        }

        auto function_names = std::vector<std::string>{};
        auto seen = std::set<std::string>{};
        for (const auto& function_node : functions_node) {
            if (!function_node.IsScalar() || function_node.Scalar().empty()) {
                std::cerr << "functions entries must be non-empty strings" << std::endl;
                return std::nullopt;
            }
            const auto function_name = function_node.Scalar();
            if (!seen.insert(function_name).second) {
                std::cerr << "duplicate function in functions: " << function_name << std::endl;
                return std::nullopt;
            }
            function_names.emplace_back(function_name);
        }
        return function_names;
    }
    if (has_function) {
        return std::vector<std::string>{vm.Get<std::string>("function")};
    }

    std::cerr << "missing required option: --function <name> or functions: [...]" << std::endl;
    return std::nullopt;
}
}  // namespace

ReturnStatus OptIR(
        const std::string& input,
        const std::string& function_name,
        const std::string& output,
        const std::vector<PassConfig>& pass_config
) {
    return OptIR(input, std::vector<std::string>{function_name}, output, pass_config);
}

ReturnStatus OptIR(
        const std::string& input,
        const std::vector<std::string>& function_names,
        const std::string& output,
        const std::vector<PassConfig>& pass_config
) {
    if (function_names.empty()) {
        std::cerr << "no functions specified" << std::endl;
        return ReturnStatus::Failure;
    }

    // Load the input json, which is a serialized IR module.
    LOG_INFO("Load IR.");
    auto ifs = std::ifstream(input);
    auto j = qret::Json::parse(ifs);

    // Deserialize IR module from json
    LOG_INFO("Load IR.");
    qret::ir::IRContext context;
    qret::ir::LoadJson(j, context);
    if (context.owned_module.empty()) {
        std::cerr << "input IR does not contain a module" << std::endl;
        return ReturnStatus::Failure;
    }
    auto* module = context.owned_module.back().get();
    auto functions = ResolveFunctions(*module, function_names);
    if (functions.size() != function_names.size()) {
        return ReturnStatus::Failure;
    }

    LOG_INFO("Optimize IR.");
    for (auto* func : functions) {
        const auto ret = RunPassesOnFunction(*func, pass_config);
        if (ret != ReturnStatus::Success) {
            return ret;
        }
    }

    LOG_INFO("Save IR.");
    return WriteModuleJsonAtomically(*module, output);
}
ReturnStatus CommandOpt::Main(int argc, const char** argv) {
    namespace po = boost::program_options;

    // Define description.
    // clang-format off
    auto description = po::options_description(R"(qret 'opt' options)");
    description.add_options()
        ("help,h", "Show this help and exit.")
        ("quiet", "Suppress non-error output.")
        ("verbose", "Enable verbose logging (more detail than default).")
        ("debug", "Enable debug logging (most detailed; implies --verbose).")
        ("color", "Enable colored output.")
        ("pipeline", po::value<std::string>(), "Pipeline file")
        ("input,i", po::value<std::string>(), "Input file")
        ("function,f", po::value<std::string>(), "Function name to optimize")
        ("output,o", po::value<std::string>(), "Output file")
        ("ir-static-condition-pruning-seed", po::value<std::uint64_t>()->default_value(0), "Seed of ir::static_condition_pruning pass.")
        ("pass", po::value<std::string>(), "Optimization pass")
    ; // NOLINT
    // clang-format on

    auto vm = VariablesMap();
    try {
        po::store(po::parse_command_line(argc, argv, description), vm.vm);
        po::notify(vm.vm);
    } catch (const po::error_with_option_name& ex) {
        std::cerr << ex.what() << std::endl;
        std::cerr << "To get the list of available options, run 'qret opt --help'." << std::endl;
        return ReturnStatus::Failure;
    }

    // Check basic options
    if (vm.Contains("help")) {
        std::cout << description;
        return ReturnStatus::Success;
    }
    if (vm.Contains("quiet")) {
        qret::Logger::DisableConsoleOutput();
        qret::Logger::DisableFileOutput();
    } else if (vm.Contains("debug")) {
        qret::Logger::EnableConsoleOutput();
        qret::Logger::SetLogLevel(qret::LogLevel::Debug);
    } else if (vm.Contains("verbose")) {
        qret::Logger::EnableConsoleOutput();
        qret::Logger::SetLogLevel(qret::LogLevel::Info);
    } else {
        qret::Logger::EnableConsoleOutput();
        qret::Logger::SetLogLevel(qret::LogLevel::Warn);
    }
    if (vm.Contains("color")) {
        qret::Logger::EnableColorfulOutput();
    } else {
        qret::Logger::DisableColorfulOutput();
    }

    // Check 'pipeline' option at first to update VariablesMap class.
    if (vm.vm.count("pipeline") > 0) {
        LOG_DEBUG("Use pipeline file to compile.");
        vm.yaml = YAML::LoadFile(vm.vm.at("pipeline").as<std::string>());
    }

    if (!vm.Contains("input")) {
        std::cerr << "missing required option: --input <file>" << std::endl;
        return ReturnStatus::Failure;
    }
    auto function_names = ParseOptFunctionNames(vm);
    if (!function_names.has_value()) {
        return ReturnStatus::Failure;
    }
    if (!vm.Contains("output")) {
        std::cerr << "missing required option: --output <file>" << std::endl;
        return ReturnStatus::Failure;
    }
    const auto input = vm.Get<std::string>("input");
    const auto output = vm.Get<std::string>("output");
    if (vm.Contains("ir-static-condition-pruning-seed")) {
        std::get<Option<std::uint64_t>*>(
                OptionStorage::GetOptionStorage()->At("ir-static-condition-pruning-seed")
        )
                ->SetValue(vm.Get<std::uint64_t>("ir-static-condition-pruning-seed"));
    }
    const auto pass_config = ParsePass(vm, "pass");

    return OptIR(input, function_names.value(), output, pass_config);
}
}  // namespace qret::cmd
