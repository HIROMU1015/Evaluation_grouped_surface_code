/**
 * @file qret/cmd/parse.cpp
 * @brief Define 'parse' sumcommand in qret.
 */

#include "qret/cmd/parse.h"

#include <boost/program_options.hpp>
#include <fmt/format.h>

#include <cstdlib>
#include <iostream>
#include <string>
#include <string_view>

#include "qret/base/json.h"
#include "qret/base/log.h"
#include "qret/base/rss_profile.h"
#include "qret/cmd/common.h"
#include "qret/frontend/builder.h"
#include "qret/frontend/openqasm2.h"
#include "qret/ir/context.h"
#include "qret/ir/function.h"
#include "qret/ir/json.h"  // DO NOT DELETE
#include "qret/ir/module.h"
#include "qret/parser/openqasm2.h"
#include "qret/parser/openqasm3.h"

namespace qret::cmd {
namespace {
bool EnvFlagEnabled(const char* name) {
    const auto* raw = std::getenv(name);
    if (raw == nullptr) {
        return false;
    }
    const auto value = std::string_view(raw);
    return !(value.empty() || value == "0" || value == "false" || value == "False");
}

bool ReleaseAstBeforeSaveEnabled() {
    return EnvFlagEnabled("QRET_PARSE_RELEASE_AST_BEFORE_SAVE");
}

std::size_t CountFunctions(const qret::ir::Module& module) {
    auto count = std::size_t{0};
    for ([[maybe_unused]] const auto& func : module) {
        ++count;
    }
    return count;
}

qret::Json ParseProfileExtra(
        const std::string& input,
        const std::string& output,
        std::size_t statement_count = 0,
        std::size_t include_count = 0,
        std::size_t function_count = 0
) {
    auto extra = qret::Json::object();
    extra["input"] = input;
    extra["output"] = output;
    extra["statement_count"] = statement_count;
    extra["include_count"] = include_count;
    extra["function_count"] = function_count;
    extra["release_ast_before_save"] = ReleaseAstBeforeSaveEnabled();
    return extra;
}
}  // namespace

ReturnStatus ParseOpenQASM2(const std::string& input, const std::string& output) {
    qret::rss_profile::Mark("parse_entry", ParseProfileExtra(input, output));

    LOG_INFO("Construct OpenQASM2 ast.");
    auto ast = qret::openqasm2::ParseOpenQASM2File(input);
    qret::rss_profile::Mark(
            "parse_after_ast_construct",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size())
    );

    LOG_INFO("Build IR from OpenQASM2 ast.");
    qret::ir::IRContext context;
    auto* module = qret::ir::Module::Create("OpenQASM2", context);
    auto builder = qret::frontend::CircuitBuilder(module);
    qret::frontend::BuildCircuitFromAST(ast, builder);
    qret::rss_profile::Mark(
            "parse_after_build_ir",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
    );

    if (ReleaseAstBeforeSaveEnabled()) {
        ast = qret::openqasm2::Program{};
        qret::rss_profile::Mark(
                "parse_after_ast_release",
                ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
        );
    }

    LOG_INFO("Save IR.");
    auto ofs = std::ofstream(output);
    if (!ofs.good()) {
        std::cerr << "failed to open: " << output << std::endl;
        return ReturnStatus::Failure;
    }

    auto j = qret::Json();
    qret::rss_profile::Mark(
            "parse_before_json_dom",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
    );
    j = *module;
    qret::rss_profile::Mark(
            "parse_after_json_dom",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
    );
    ofs << j << std::endl;
    ofs.close();
    qret::rss_profile::Mark(
            "parse_after_stream_write",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
    );

    return ReturnStatus::Success;
}
ReturnStatus ParseOpenQASM3(const std::string& input, const std::string& output) {
    qret::rss_profile::Mark("parse_entry", ParseProfileExtra(input, output));

    LOG_INFO("Construct OpenQASM3 ast.");
    auto ast = qret::openqasm3::ParseOpenQASM3File(input);
    qret::rss_profile::Mark(
            "parse_after_ast_construct",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size())
    );

    LOG_INFO("Build IR from OpenQASM3 ast.");
    qret::ir::IRContext context;
    auto* module = qret::ir::Module::Create("OpenQASM3", context);
    auto builder = qret::frontend::CircuitBuilder(module);
    qret::frontend::BuildCircuitFromAST(ast, builder);
    qret::rss_profile::Mark(
            "parse_after_build_ir",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
    );

    if (ReleaseAstBeforeSaveEnabled()) {
        ast = qret::openqasm2::Program{};
        qret::rss_profile::Mark(
                "parse_after_ast_release",
                ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
        );
    }

    LOG_INFO("Save IR.");
    auto ofs = std::ofstream(output);
    if (!ofs.good()) {
        std::cerr << "failed to open: " << output << std::endl;
        return ReturnStatus::Failure;
    }

    auto j = qret::Json();
    qret::rss_profile::Mark(
            "parse_before_json_dom",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
    );
    j = *module;
    qret::rss_profile::Mark(
            "parse_after_json_dom",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
    );
    ofs << j << std::endl;
    ofs.close();
    qret::rss_profile::Mark(
            "parse_after_stream_write",
            ParseProfileExtra(input, output, ast.sts.size(), ast.incls.size(), CountFunctions(*module))
    );

    return ReturnStatus::Success;
}
ReturnStatus Parse(const std::string& input, const std::string& output, const std::string& format) {
    if (format == "OpenQASM2") {
        return ParseOpenQASM2(input, output);
    } else if (format == "OpenQASM3") {
        return ParseOpenQASM3(input, output);
    }
    std::cerr << "unknown format: " << format << ". expected OpenQASM2 or OpenQASM3" << std::endl;
    return ReturnStatus::Failure;
}
ReturnStatus CommandParse::Main(int argc, const char** argv) {
    namespace po = boost::program_options;

    // Define description.
    // clang-format off
    auto description = po::options_description(R"(qret 'parse' options)");
    description.add_options()
        ("help,h", "Show this help and exit.")
        ("quiet", "Suppress non-error output.")
        ("verbose", "Enable verbose logging (more detail than default).")
        ("debug", "Enable debug logging (most detailed; implies --verbose).")
        ("color", "Enable colored output.")
        ("input,i", po::value<std::string>(), "Input file")
        ("output,o", po::value<std::string>()->default_value("ir.json"), "Output file")
        ("format,f", po::value<std::string>()->default_value("OpenQASM2"), "Format of input file ('OpenQASM2' or 'OpenQASM3'). OpenQASM3 is a compatibility subset.")
    ; // NOLINT
    // clang-format on

    auto vm = po::variables_map();
    try {
        po::store(po::parse_command_line(argc, argv, description), vm);
        po::notify(vm);
    } catch (const po::error_with_option_name& ex) {
        std::cerr << ex.what() << std::endl;
        std::cerr << "To get the list of available options, run 'qret parse --help'." << std::endl;
        return ReturnStatus::Failure;
    }

    if (vm.count("help") > 0) {
        std::cout << description;
        return ReturnStatus::Success;
    }
    if (vm.count("quiet") > 0) {
        qret::Logger::DisableConsoleOutput();
        qret::Logger::DisableFileOutput();
    } else if (vm.count("debug") > 0) {
        qret::Logger::EnableConsoleOutput();
        qret::Logger::SetLogLevel(qret::LogLevel::Debug);
    } else if (vm.count("verbose") > 0) {
        qret::Logger::EnableConsoleOutput();
        qret::Logger::SetLogLevel(qret::LogLevel::Info);
    } else {
        qret::Logger::EnableConsoleOutput();
        qret::Logger::SetLogLevel(qret::LogLevel::Warn);
    }
    if (vm.count("color") > 0) {
        qret::Logger::EnableColorfulOutput();
    } else {
        qret::Logger::DisableColorfulOutput();
    }

    if (vm.count("input") == 0) {
        std::cerr << "missing required option: --input <file>" << std::endl;
        return ReturnStatus::Failure;
    }

    const auto input = vm["input"].as<std::string>();
    const auto output = vm["output"].as<std::string>();
    const auto format = vm["format"].as<std::string>();

    return Parse(input, output, format);
}
}  // namespace qret::cmd
