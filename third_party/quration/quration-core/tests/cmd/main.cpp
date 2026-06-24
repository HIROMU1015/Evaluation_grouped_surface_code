#include "qret/cmd/main.h"

#include <gtest/gtest.h>

#include <chrono>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "qret/base/json.h"
#include "qret/cmd/common.h"
#include "qret/parser/openqasm2.h"

static constexpr auto BinName = "qret";

namespace {
std::filesystem::path MakeTempPath(const std::string& suffix) {
    static std::uint64_t counter = 0;
    const auto tick = std::chrono::steady_clock::now().time_since_epoch().count();
    return std::filesystem::temp_directory_path()
            / ("qret_cmd_main_" + std::to_string(tick) + "_" + std::to_string(counter++) + suffix);
}

void CompileFixtureToScLsFixedV0(const std::filesystem::path& output_path) {
    const auto output = output_path.string();
    const auto circuit_name = std::string("AddCuccaro(3)");
    const auto input_file = std::string("quration-core/tests/data/circuit/add_cuccaro_3.json");
    const auto topology_file = std::string("quration-core/tests/data/topology/plane.yaml");

    // Build a small SC_LS_FIXED_V0 pipeline state used by asm/profile integration tests.
    auto argv = std::vector<const char*>{
            BinName,
            "compile",
            "--input",
            input_file.c_str(),
            "--function",
            circuit_name.c_str(),
            "--output",
            output.c_str(),
            "--sc_ls_fixed_v0_topology",
            topology_file.c_str(),
    };
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
    EXPECT_TRUE(std::filesystem::exists(output_path));
}

std::string ReadFile(const std::filesystem::path& path) {
    auto ifs = std::ifstream(path);
    EXPECT_TRUE(ifs.good());

    auto ss = std::stringstream();
    ss << ifs.rdbuf();
    return ss.str();
}

void WriteFile(const std::filesystem::path& path, const std::string& text) {
    auto ofs = std::ofstream(path);
    EXPECT_TRUE(ofs.good());
    ofs << text;
}

std::filesystem::path WriteOptFixtureIr() {
    const auto input = MakeTempPath(".opt_input.json");
    WriteFile(
            input,
            R"json({
  "metadata": {
    "format": "IR",
    "schema_version": "0.1",
    "qret_version": "0.7.1",
    "created_at": "2026-01-01T00:00:00"
  },
  "name": "multi_function_opt",
  "circuit_list": [
    {
      "name": "helper_a",
      "entry_point": "entry",
      "bb_list": [
        {
          "name": "entry",
          "inst_list": [
            {"opcode": "X", "q": 0},
            {"opcode": "X", "q": 0},
            {"opcode": "Return"}
          ],
          "predecessors": [],
          "successors": []
        }
      ],
      "argument": {"num_qubits": 1, "qubits": {"q": 1}, "num_registers": 0},
      "num_tmp_registers": 0
    },
    {
      "name": "helper_b",
      "entry_point": "entry",
      "bb_list": [
        {
          "name": "entry",
          "inst_list": [
            {"opcode": "Y", "q": 0},
            {"opcode": "Y", "q": 0},
            {"opcode": "Return"}
          ],
          "predecessors": [],
          "successors": []
        }
      ],
      "argument": {"num_qubits": 1, "qubits": {"q": 1}, "num_registers": 0},
      "num_tmp_registers": 0
    },
    {
      "name": "helper_c",
      "entry_point": "entry",
      "bb_list": [
        {
          "name": "entry",
          "inst_list": [
            {"opcode": "Z", "q": 0},
            {"opcode": "Z", "q": 0},
            {"opcode": "Return"}
          ],
          "predecessors": [],
          "successors": []
        }
      ],
      "argument": {"num_qubits": 1, "qubits": {"q": 1}, "num_registers": 0},
      "num_tmp_registers": 0
    },
    {
      "name": "untouched",
      "entry_point": "entry",
      "bb_list": [
        {
          "name": "entry",
          "inst_list": [
            {"opcode": "X", "q": 0},
            {"opcode": "X", "q": 0},
            {"opcode": "Return"}
          ],
          "predecessors": [],
          "successors": []
        }
      ],
      "argument": {"num_qubits": 1, "qubits": {"q": 1}, "num_registers": 0},
      "num_tmp_registers": 0
    }
  ]
})json"
    );
    return input;
}

std::filesystem::path WriteOptPipeline(
        const std::filesystem::path& input,
        const std::filesystem::path& output,
        const std::string& function_spec
) {
    const auto pipeline = MakeTempPath(".opt_pipeline.yaml");
    WriteFile(
            pipeline,
            "input: " + input.string() + "\n"
                    + function_spec
                    + "output: " + output.string() + "\n"
                    + "pass:\n"
                    + "  - ir::delete_consecutive_same_pauli\n"
    );
    return pipeline;
}

qret::Json ReadJson(const std::filesystem::path& path) {
    auto ifs = std::ifstream(path);
    EXPECT_TRUE(ifs.good());
    return qret::Json::parse(ifs);
}

qret::Json FunctionJson(const std::filesystem::path& path, const std::string& function_name) {
    const auto json = ReadJson(path);
    for (const auto& circuit : json["circuit_list"]) {
        if (circuit["name"] == function_name) {
            return circuit;
        }
    }
    ADD_FAILURE() << "function not found: " << function_name;
    return nullptr;
}

std::vector<std::string> FunctionOpcodes(
        const std::filesystem::path& path,
        const std::string& function_name
) {
    const auto function = FunctionJson(path, function_name);
    auto opcodes = std::vector<std::string>{};
    for (const auto& inst : function["bb_list"][0]["inst_list"]) {
        opcodes.emplace_back(inst["opcode"].get<std::string>());
    }
    return opcodes;
}

void RunOptPipeline(const std::filesystem::path& pipeline) {
    const auto pipeline_str = pipeline.string();
    auto argv = std::vector<const char*>{BinName, "opt", "--pipeline", pipeline_str.c_str()};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}

void RunOptCli(
        const std::filesystem::path& input,
        const std::string& function_name,
        const std::filesystem::path& output
) {
    const auto input_str = input.string();
    const auto output_str = output.string();
    const auto pass = std::string("ir::delete_consecutive_same_pauli");
    auto argv = std::vector<const char*>{
            BinName,
            "opt",
            "--input",
            input_str.c_str(),
            "--function",
            function_name.c_str(),
            "--output",
            output_str.c_str(),
            "--pass",
            pass.c_str(),
    };
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
}  // namespace

TEST(QretMain, NoArgument) {
    auto argv = std::vector<const char*>{BinName};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMain, Help) {
    auto argv = std::vector<const char*>{BinName, "help"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMain, BH) {
    auto argv = std::vector<const char*>{BinName, "-h"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMain, BBHelp) {
    auto argv = std::vector<const char*>{BinName, "--help"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMain, Version) {
    auto argv = std::vector<const char*>{BinName, "version"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMain, BV) {
    auto argv = std::vector<const char*>{BinName, "-v"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMain, BBVersion) {
    auto argv = std::vector<const char*>{BinName, "--version"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMain, UnknownCommand) {
    auto argv = std::vector<const char*>{BinName, "--hep"};
    EXPECT_EQ(1, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMainCompile, BBHelp) {
    auto argv = std::vector<const char*>{BinName, "compile", "--help"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMainAsm, BBHelp) {
    auto argv = std::vector<const char*>{BinName, "asm", "--help"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMainParse, BBHelp) {
    auto argv = std::vector<const char*>{BinName, "parse", "--help"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMainOpt, BBHelp) {
    auto argv = std::vector<const char*>{BinName, "opt", "--help"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMainOpt, ScalarFunctionCliCompatibility) {
    const auto input = WriteOptFixtureIr();
    const auto output = MakeTempPath(".opt_scalar_output.json");

    RunOptCli(input, "helper_a", output);

    EXPECT_EQ(FunctionOpcodes(output, "helper_a"), std::vector<std::string>({"Return"}));
    EXPECT_EQ(
            FunctionOpcodes(output, "helper_b"),
            std::vector<std::string>({"Y", "Y", "Return"})
    );
    EXPECT_EQ(
            FunctionOpcodes(output, "untouched"),
            std::vector<std::string>({"X", "X", "Return"})
    );
}
TEST(QretMainOpt, MultipleFunctionsPipeline) {
    const auto input = WriteOptFixtureIr();
    const auto output = MakeTempPath(".opt_multi_output.json");
    const auto pipeline = WriteOptPipeline(
            input,
            output,
            "functions:\n"
            "  - helper_a\n"
            "  - helper_b\n"
            "  - helper_c\n"
    );

    RunOptPipeline(pipeline);

    EXPECT_EQ(FunctionOpcodes(output, "helper_a"), std::vector<std::string>({"Return"}));
    EXPECT_EQ(FunctionOpcodes(output, "helper_b"), std::vector<std::string>({"Return"}));
    EXPECT_EQ(FunctionOpcodes(output, "helper_c"), std::vector<std::string>({"Return"}));
    EXPECT_EQ(
            FunctionOpcodes(output, "untouched"),
            std::vector<std::string>({"X", "X", "Return"})
    );
}
TEST(QretMainOpt, MultipleFunctionsMatchesIndividualReferenceAndOrderIndependent) {
    const auto input = WriteOptFixtureIr();
    const auto individual_a = MakeTempPath(".opt_individual_a.json");
    const auto individual_b = MakeTempPath(".opt_individual_b.json");
    const auto individual_c = MakeTempPath(".opt_individual_c.json");
    RunOptCli(input, "helper_a", individual_a);
    RunOptCli(individual_a, "helper_b", individual_b);
    RunOptCli(individual_b, "helper_c", individual_c);

    const auto batch = MakeTempPath(".opt_batch.json");
    RunOptPipeline(WriteOptPipeline(
            input,
            batch,
            "functions:\n"
            "  - helper_a\n"
            "  - helper_b\n"
            "  - helper_c\n"
    ));

    const auto reverse = MakeTempPath(".opt_reverse.json");
    RunOptPipeline(WriteOptPipeline(
            input,
            reverse,
            "functions:\n"
            "  - helper_c\n"
            "  - helper_b\n"
            "  - helper_a\n"
    ));

    for (const auto& function_name : {"helper_a", "helper_b", "helper_c", "untouched"}) {
        EXPECT_EQ(FunctionJson(batch, function_name), FunctionJson(individual_c, function_name));
        EXPECT_EQ(FunctionJson(reverse, function_name), FunctionJson(individual_c, function_name));
    }
}
TEST(QretMainOpt, InvalidFunctionSchemaFails) {
    const auto input = WriteOptFixtureIr();
    const auto cases = std::vector<std::string>{
            "",
            "function: helper_a\nfunctions:\n  - helper_b\n",
            "functions: []\n",
            "functions:\n  - helper_a\n  - helper_a\n",
            "functions:\n  - {name: helper_a}\n",
            "functions:\n  - unknown\n",
    };
    for (std::size_t i = 0; i < cases.size(); ++i) {
        const auto output = MakeTempPath(".opt_invalid_output.json");
        const auto pipeline = WriteOptPipeline(input, output, cases[i]);
        const auto pipeline_str = pipeline.string();
        auto argv = std::vector<const char*>{BinName, "opt", "--pipeline", pipeline_str.c_str()};
        EXPECT_EQ(1, qret::cmd::QretMain(argv.size(), argv.data())) << "case index: " << i;
        EXPECT_FALSE(std::filesystem::exists(output));
    }
}
TEST(QretMainProfile, BBHelp) {
    auto argv = std::vector<const char*>{BinName, "profile", "--help"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMainSimulate, BBHelp) {
    auto argv = std::vector<const char*>{BinName, "simulate", "--help"};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
}
TEST(QretMainAsm, FromScLsFixedV0PipelineState) {
    const auto pipeline_state_file = MakeTempPath(".pipeline_state.json");
    const auto asm_file = MakeTempPath(".out.asm");
    CompileFixtureToScLsFixedV0(pipeline_state_file);

    const auto input = pipeline_state_file.string();
    const auto output = asm_file.string();
    auto argv = std::vector<const char*>{BinName, "asm", input.c_str(), output.c_str()};
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
    EXPECT_TRUE(std::filesystem::exists(asm_file));
    EXPECT_FALSE(ReadFile(asm_file).empty());
}
TEST(QretMainProfile, JsonAndMarkdownFromScLsFixedV0PipelineState) {
    const auto pipeline_state_file = MakeTempPath(".pipeline_state.json");
    const auto json_file = MakeTempPath(".compile_info.json");
    const auto markdown_file = MakeTempPath(".compile_info.md");
    CompileFixtureToScLsFixedV0(pipeline_state_file);

    const auto input = pipeline_state_file.string();
    const auto json_output = json_file.string();
    auto argv_json =
            std::vector<const char*>{BinName, "profile", input.c_str(), json_output.c_str()};
    EXPECT_EQ(0, qret::cmd::QretMain(argv_json.size(), argv_json.data()));
    EXPECT_TRUE(std::filesystem::exists(json_file));
    EXPECT_NE(std::string::npos, ReadFile(json_file).find("\"runtime\""));

    const auto markdown_output = markdown_file.string();
    auto argv_markdown = std::vector<const char*>{
            BinName,
            "profile",
            "--format",
            "markdown",
            input.c_str(),
            markdown_output.c_str(),
    };
    EXPECT_EQ(0, qret::cmd::QretMain(argv_markdown.size(), argv_markdown.data()));
    EXPECT_TRUE(std::filesystem::exists(markdown_file));
    EXPECT_NE(std::string::npos, ReadFile(markdown_file).find("Compile information"));
}
TEST(QretMainCompile, OpenQASM2Source) {
    if (!qret::openqasm2::CanParseOpenQASM2()) {
        GTEST_SKIP() << "Skip OpenQASM2 test";
    }
    const auto output = "qret_compile_openqasm2_from_cmd.json";
    auto argv = std::vector<const char*>{
            BinName,
            "compile",
            "--input",
            "quration-core/tests/data/OpenQASM2/x.qasm",
            "--source",
            "OpenQASM2",
            "--target",
            "SC_LS_FIXED_V0",
            "--output",
            output,
            "--sc_ls_fixed_v0_topology",
            "quration-core/tests/data/topology/plane.yaml",
            "--sc_ls_fixed_v0_pass",
            "sc_ls_fixed_v0::mapping,sc_ls_fixed_v0::routing",
    };
    EXPECT_EQ(0, qret::cmd::QretMain(argv.size(), argv.data()));
    EXPECT_TRUE(std::filesystem::exists(output));
}
