from __future__ import annotations

import os
import shutil
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lints

SHIM = "c" "md"
BARE = SHIM + " /c extract.cmd\n"
NAMED = "@echo off\n" + SHIM + ".exe /c extract.cmd\ncall rebuild.cmd\n"
POOL = "\n".join(["import multiprocessing", "", "def run():",
                  "    return multiprocessing.Pool(2)"])
POOL_GUARDED = POOL + '\n\nif __name__ == "__main__":\n    run()\n'
DRIVE = "C" + ":"
OUTSIDE = 'import sys\nsys.path.insert(0, r"%s\\\\temp\\\\clone\\\\tools\\\\formats")\n' % DRIVE
INSIDE = 'import sys, os\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n'
MARKED = "/* NONMATCHING-REFERENCE: reconstructed, not linked. */\nvoid Unit_DoIt(void) {\n}\n"
UNMARKED = "void Unit_DoIt(void) {\n}\n"
LOWERCASE_VERB = "void Unit_doit(void) {\n}\n"
CONVENTION_NAMES = ("void Unit_DoIt(void) {\n}\nvoid sub_080143F2(void) {\n}\n"
                    "void sub_0801C62C(void) {\n}\n")
MEASURED = (64, 8388608, "0.0008")
SPLIT = {"proven code": 3904, "filtered pointer-entry code": 53934, "literal pool": 3546,
         "IWRAM overlay": 3708, "unclassified": 8323516}
SPLIT_PROGRESS = ("proven code 3,904 B, filtered pointer-entry code 53,934 B, literal pool "
                  "3,546 B, overlay 3,708 B, unclassified 8,323,516 B")
STALE_PROGRESS = ("The source-built surface is 2,004,828 of 8,388,608 bytes (23.8994 %).")
MEASURED_PROGRESS = ("0.0008 % of the ROM (64 of 8,388,608 bytes) is built from this "
                     "repository's sources; `python tools\\gate\\gate.py` prints it.")
BYTES_FIRST = ("64 of 8,388,608 bytes (0.0008 %) is built from this repository's "
               "sources; `python tools\\gate\\gate.py` prints it.")
BLOCK = ("def %s():\n"
         "    first = 1\n"
         "    second = first + 1\n"
         "    third = second * 2\n"
         "    fourth = third - 3\n"
         "    fifth = fourth / 4\n"
         "    sixth = fifth + 6\n"
         "    seventh = sixth - 7\n"
         "    return seventh\n")
PLANTED_DUPLICATE = BLOCK % "left" + "\n" + BLOCK % "right"
ONE_COPY = BLOCK % "left"
SILENT_RETURN = ("import os\n"
                 "\n"
                 "\n"
                 "def test_the_image_is_there():\n"
                 "    if not os.path.exists('baserom.gba'):\n"
                 "        return\n"
                 "    assert True\n")
SKIPPED = ("import os\n"
           "import pytest\n"
           "\n"
           "\n"
           "def test_the_image_is_there():\n"
           "    if not os.path.exists('baserom.gba'):\n"
           "        pytest.skip('baserom.gba is absent, so this test cannot run')\n"
           "    assert True\n")
NESTED_HELPER = ("def test_the_helper_may_return():\n"
                 "    def check():\n"
                 "        return 1\n"
                 "    assert check() == 1\n")
EARLY_RETURN_AFTER_ASSERT = ("def test_the_population_is_measured():\n"
                             "    rows = read()\n"
                             "    assert rows\n"
                             "    if len(rows) < 2:\n"
                             "        return\n"
                             "    assert rows[1]\n")
ASSERT_IN_ONE_BRANCH = ("def test_the_image_is_there():\n"
                        "    if present():\n"
                        "        assert True\n"
                        "        return\n"
                        "    return\n")
MATCH_RETURN = ("def test_the_fixture_is_there():\n"
                "    match read():\n"
                "        case None:\n"
                "            return\n"
                "        case _:\n"
                "            assert True\n")
FOREIGN_SKIP = ("def test_the_image_is_there():\n"
                "    reporter.skip()\n"
                "    return\n")
C_COMMENTED_DUPLICATE = ("/* the header\n"
                         "   spans three\n"
                         "   physical lines */\n"
                         "static void unit_left(void) {\n"
                         "    unsigned first = 1;\n"
                         "    unsigned second = first + 1;\n"
                         "    unsigned third = second * 2;\n"
                         "    unsigned fourth = third - 3;\n"
                         "    unsigned fifth = fourth / 4;\n"
                         "    unsigned sixth = fifth + 6;\n"
                         "    unsigned seventh = sixth - 7;\n"
                         "}\n"
                         "\n"
                         "static void unit_right(void) {\n"
                         "    unsigned first = 1;\n"
                         "    unsigned second = first + 1;\n"
                         "    unsigned third = second * 2;\n"
                         "    unsigned fourth = third - 3;\n"
                         "    unsigned fifth = fourth / 4;\n"
                         "    unsigned sixth = fifth + 6;\n"
                         "    unsigned seventh = sixth - 7;\n"
                         "}\n")


CALL = "call tools\\incbin.bat baserom.gba 0x158 0x143f2\n"

NAMES = "address,name\n0x08000276,Unit_DoIt\n"
LEDGER = ("address,old,new,evidence_class,evidence\n"
          "0x08000276,sub_08000276,Unit_DoIt,device-register,IE (0x04000200) bit 1\n")
ENTRIES = {0x08000276}
README_FUNCTIONS = "1 of the 2 functions still carry the address form\n"
BASELINE = "1\n"


def refused(text, name, check):
    scratch = tempfile.mkdtemp(prefix="lint-test-")
    try:
        path = os.path.join(scratch, name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return [detail for found, detail in lints.run([path]) if found == check]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


PROLOGUE = ("from __future__ import annotations\nimport hashlib\nimport io\nimport os\n"
            "import re\nimport struct\nimport sys\nimport tokenize\n")

ANSWER_CASES = (
    pytest.param(BARE, "step.cmd", "P-159-bare-interpreter", True,
                 id="a_bare_interpreter_launch_in_a_step_script_is_caught"),
    pytest.param(NAMED, "step.cmd", "P-159-bare-interpreter", False,
                 id="the_executable_name_and_a_sibling_script_are_not_caught"),
    pytest.param(POOL, "probe.py", "P-167-pool-guard", True,
                 id="a_pool_in_a_module_with_no_main_guard_is_caught"),
    pytest.param(POOL_GUARDED, "probe.py", "P-167-pool-guard", False,
                 id="the_same_pool_under_a_main_guard_is_not_caught"),
    pytest.param(OUTSIDE, "tool.py", "P-148-repo-module-path", True,
                 id="a_search_path_leaving_the_repository_is_caught"),
    pytest.param(INSIDE, "tool.py", "P-148-repo-module-path", False,
                 id="a_search_path_inside_the_repository_is_not_caught"),
    pytest.param(ONE_COPY, "tool.py", "DUP-block", False,
                 id="a_block_written_once_is_not_caught"),
    pytest.param(PROLOGUE + PROLOGUE, "tool.py", "DUP-block", False,
                 id="a_repeated_import_prologue_is_not_a_duplicate"),
    pytest.param(SKIPPED, "test_image.py", "TEST-silent-return", False,
                 id="a_test_that_skips_with_a_reason_is_not_caught"),
    pytest.param(NESTED_HELPER, "test_image.py", "TEST-silent-return", False,
                 id="a_helper_defined_inside_a_test_may_return"),
    pytest.param(EARLY_RETURN_AFTER_ASSERT, "test_image.py", "TEST-silent-return", False,
                 id="a_return_after_an_assert_is_not_caught"),
)


@pytest.mark.parametrize("text,name,check,caught", ANSWER_CASES)
def test_the_lint_answer_to_one_input(text, name, check, caught):
    found = refused(text, name, check)
    assert bool(found) == caught


CAUGHT_CASES = (
    pytest.param(PLANTED_DUPLICATE, "tool.py", "DUP-block",
                 ("tool.py:2 and", "tool.py:12: 8 identical lines"),
                 id="a_block_written_twice_in_one_file_is_caught"),
    pytest.param(SILENT_RETURN, "test_image.py", "TEST-silent-return",
                 (":6: test_the_image_is_there",),
                 id="a_test_that_returns_when_its_fixture_is_missing_is_caught"),
    pytest.param(ASSERT_IN_ONE_BRANCH, "test_image.py", "TEST-silent-return",
                 (":5: test_the_image_is_there",),
                 id="an_assert_inside_one_branch_does_not_clear_a_return_in_another"),
    pytest.param(MATCH_RETURN, "test_image.py", "TEST-silent-return",
                 (":4: test_the_fixture_is_there",),
                 id="a_return_inside_a_match_case_is_caught"),
    pytest.param(FOREIGN_SKIP, "test_image.py", "TEST-silent-return",
                 (":3: test_the_image_is_there",),
                 id="a_skip_on_an_unrelated_object_does_not_clear_a_return"),
)


@pytest.mark.parametrize("text,name,check,fragments", CAUGHT_CASES)
def test_a_refused_run_names_the_lines_it_refused(text, name, check, fragments):
    found = refused(text, name, check)
    assert len(found) == 1, found
    assert [fragment for fragment in fragments if fragment not in found[0]] == [], found


def test_a_function_name_outside_the_convention_is_caught():
    assert lints.function_name_findings("src/Unit.c", LOWERCASE_VERB)


def test_module_verb_and_sub_08xxxxxx_names_are_not_caught():
    assert not lints.function_name_findings("src/Unit.c", CONVENTION_NAMES)


def test_a_c_source_the_build_skips_and_does_not_mark_is_caught():
    assert lints.c_status_findings("src/Unit.c", UNMARKED, compiled=set())


def test_a_c_source_the_build_skips_and_marks_is_not_caught():
    assert not lints.c_status_findings("src/Unit.c", MARKED, compiled=set())


def test_a_c_source_the_build_compiles_and_marks_is_caught():
    assert lints.c_status_findings("src/sub_0801C62C.c", MARKED, compiled={"src/sub_0801C62C.c"})


def test_a_c_source_the_build_compiles_and_does_not_mark_is_not_caught():
    assert not lints.c_status_findings("src/sub_0801C62C.c", UNMARKED,
                                       compiled={"src/sub_0801C62C.c"})


def test_a_marker_below_the_header_does_not_satisfy_the_check():
    body_marker = "void Unit_DoIt(void) {\n    /* NONMATCHING-REFERENCE */\n}\n"
    assert lints.c_status_findings("src/Unit.c", body_marker, compiled=set())


def test_a_tracked_rom_path_is_caught():
    assert lints.tracked_image_name("baserom.gba")


def test_a_tracked_source_path_is_not_caught():
    assert not lints.tracked_image_name("src/GBARam.c")


def test_the_tracked_retail_hash_file_is_not_caught():
    assert not lints.tracked_image_name("baserom.sha1")


def test_a_tracked_file_over_a_megabyte_outside_assets_is_caught():
    assert lints.oversize_tracked("tools/big.bin", 2 * 1024 * 1024)


def test_a_tracked_file_over_a_megabyte_under_assets_is_not_caught():
    assert not lints.oversize_tracked("assets/big.bin", 2 * 1024 * 1024)


def test_the_stale_readme_progress_line_is_caught():
    assert lints.readme_numbers_findings(STALE_PROGRESS, *MEASURED)


def test_a_one_digit_percentage_change_is_caught():
    assert lints.readme_numbers_findings(MEASURED_PROGRESS.replace("0.0008", "0.0009"),
                                         *MEASURED)


def test_a_one_digit_byte_count_change_is_caught():
    assert lints.readme_numbers_findings(MEASURED_PROGRESS.replace("64 of", "65 of"),
                                         *MEASURED)


def test_the_measured_readme_progress_line_is_not_caught():
    assert not lints.readme_numbers_findings(MEASURED_PROGRESS, *MEASURED)


def test_a_readme_with_the_bytes_first_is_not_caught():
    assert not lints.readme_numbers_findings(BYTES_FIRST, *MEASURED)


def test_a_second_percentage_is_caught():
    assert lints.readme_numbers_findings(MEASURED_PROGRESS + " 1.0000 % extra", *MEASURED)


def test_a_progress_line_without_its_command_is_caught():
    assert lints.readme_numbers_findings(
        MEASURED_PROGRESS.replace("`python tools\\gate\\gate.py` ", ""), *MEASURED)


def test_the_readme_split_figure_matching_the_document_is_not_caught():
    assert not lints.readme_split_findings(SPLIT_PROGRESS, SPLIT)


def test_a_one_digit_split_figure_change_is_caught():
    assert lints.readme_split_findings(SPLIT_PROGRESS.replace("53,934", "53,933"), SPLIT)


def test_a_readme_without_the_split_figure_is_caught():
    assert lints.readme_split_findings(MEASURED_PROGRESS, SPLIT)


def test_an_incbin_call_naming_a_slice_no_source_incbins_is_caught():
    assert lints.stale_call_findings(CALL, set())


def test_an_incbin_call_naming_a_slice_the_source_incbins_is_not_caught():
    assert not lints.stale_call_findings(CALL, {(0x158, 0x143f2 - 0x158)})


def test_a_name_keyed_on_an_address_the_split_does_not_prove_is_caught():
    findings, _names = lints.naming_symbol_findings(
        "address,name\n0x08000276,Unit_DoIt\n0x08000278,Unit_DoThat\n", LEDGER, ENTRIES)
    assert [(found, detail) for found, detail in findings
            if "0x08000278 is not a code entry" in detail]


def test_a_name_outside_module_verb_is_caught():
    findings, _names = lints.naming_symbol_findings(
        "address,name\n0x08000276,unit_doit\n",
        LEDGER.replace("Unit_DoIt", "unit_doit"), ENTRIES)
    assert [(found, detail) for found, detail in findings if "is not Module_Verb" in detail]


def test_a_repeated_name_is_caught():
    table = ("address,name\n0x08000276,Unit_DoIt\n0x08000278,Unit_DoIt\n")
    findings, _names = lints.naming_symbol_findings(table, LEDGER, ENTRIES | {0x08000278})
    assert [(found, detail) for found, detail in findings if "repeats the name" in detail]


def test_a_name_without_a_ledger_row_is_caught():
    findings, _names = lints.naming_symbol_findings(NAMES, None, ENTRIES)
    assert [(found, detail) for found, detail in findings if "carries no ledger row" in detail]


def test_a_ledger_row_that_disagrees_with_the_table_is_caught():
    findings, _names = lints.naming_symbol_findings(
        NAMES, LEDGER.replace(",Unit_DoIt,", ",Unit_DoThat,"), ENTRIES)
    assert [(found, detail) for found, detail in findings
            if "is not the name table's name" in detail]


def test_a_ledger_row_without_an_evidence_cell_is_caught():
    findings, _names = lints.naming_symbol_findings(
        NAMES, "address,old,new,evidence_class,evidence\n"
               "0x08000276,sub_08000276,Unit_DoIt,device-register,\n", ENTRIES)
    assert [(found, detail) for found, detail in findings
            if "needs an evidence class and an evidence cell" in detail]


def test_a_table_that_matches_the_ledger_and_the_entries_is_not_caught():
    findings, names = lints.naming_symbol_findings(NAMES, LEDGER, ENTRIES)
    assert findings == []
    assert names == {0x08000276: "Unit_DoIt"}


def test_a_name_on_an_interior_fragment_is_caught():
    findings, _names = lints.naming_symbol_findings(NAMES, LEDGER, ENTRIES, set())
    assert [(found, detail) for found, detail in findings
            if "is an interior fragment, not a function start" in detail]


def test_a_name_on_a_function_start_is_not_caught():
    findings, names = lints.naming_symbol_findings(NAMES, LEDGER, ENTRIES, {0x08000276})
    assert findings == []
    assert names == {0x08000276: "Unit_DoIt"}


def test_an_address_named_count_above_the_baseline_is_caught():
    findings = lints.naming_ratchet_findings({0x08000276, 0x08000278}, {}, "1\n")
    assert [detail for _found, detail in findings if "above the baseline 1" in detail]


def test_an_address_named_count_below_an_unlowered_baseline_is_caught():
    findings = lints.naming_ratchet_findings({0x08000276}, {0x08000276: "Unit_DoIt"}, "2\n")
    assert [detail for _found, detail in findings if "must lower" in detail]


def test_an_address_named_count_matching_the_baseline_is_not_caught():
    assert lints.naming_ratchet_findings({0x08000276, 0x08000278},
                                         {0x08000276: "Unit_DoIt"}, "1\n") == []


def test_a_baseline_that_carries_no_count_is_caught():
    assert lints.naming_ratchet_findings({0x08000276}, {}, None)


def test_readme_function_figures_that_match_the_tree_are_not_caught():
    assert lints.readme_naming_findings(README_FUNCTIONS, 1, 2) == []


def test_the_function_figure_is_held_in_both_directions():
    assert lints.readme_naming_findings(README_FUNCTIONS.replace("1 of", "0 of"), 0, 2) == []
    assert lints.readme_naming_findings(README_FUNCTIONS, 0, 2)


def test_a_readme_without_the_function_figure_is_caught():
    assert lints.readme_naming_findings(MEASURED_PROGRESS, 1, 2)


LIB_TABLE = "address,name\n0x08000276,strlen\n"
LIB_ROW = ("address,old,new,evidence_class,evidence\n"
           "0x08000276,sub_08000276,strlen,toolchain-library,"
           "armlib/c_t__un.l member strlen.o symbol strlen 76 B matched\n")


def test_a_library_symbol_with_its_row_is_not_caught():
    findings, names = lints.naming_symbol_findings(LIB_TABLE, LIB_ROW, {0x08000276})
    assert findings == []
    assert names == {0x08000276: "strlen"}


def test_a_library_symbol_without_its_row_is_caught():
    findings, _names = lints.naming_symbol_findings(
        LIB_TABLE, "address,old,new,evidence_class,evidence\n", {0x08000276})
    assert [detail for _found, detail in findings
            if "no toolchain-library ledger row names it" in detail]


def test_the_repository_has_no_lint_finding():

    assert lints.run() == []


def test_a_pair_named_in_the_allowlist_is_cleared():
    scratch = tempfile.mkdtemp(prefix="lint-test-")
    try:
        path = os.path.join(scratch, "tool.py")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(PLANTED_DUPLICATE)
        first, second, _ = lints.duplicate_blocks([path])[0]
        saved = lints.DUP_ALLOWLIST
        lints.DUP_ALLOWLIST = ((first[0], first[1], second[0], second[1], "measured"),)
        try:
            assert not [detail for found, detail in lints.run([path]) if found == "DUP-block"]
        finally:
            lints.DUP_ALLOWLIST = saved
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def test_a_multiline_c_comment_keeps_the_reported_line_numbers():
    found = refused(C_COMMENTED_DUPLICATE, "unit.c", "DUP-block")
    assert len(found) == 1, found
    assert "unit.c:5 and" in found[0], found
    assert "unit.c:15: 8 identical lines" in found[0], found


def test_a_split_figure_wrapped_across_lines_is_read():
    wrapped = SPLIT_PROGRESS.replace("filtered pointer-entry", "filtered\npointer-entry")
    assert not lints.readme_split_findings(wrapped, SPLIT)


def test_a_line_comment_marker_inside_a_string_is_not_a_comment():
    assert lints.c_lines('printf("http://x");\n') == [(1, 'printf("http://x");')]


def test_a_block_comment_marker_inside_a_string_hides_nothing():
    text = 'puts("/*");\nint kept = 1;\n/* real */\nint tail = 2;\n'
    assert lints.c_lines(text) == [(1, 'puts("/*");'), (2, "int kept = 1;"), (3, ""),
                                   (4, "int tail = 2;")]


def test_an_inline_block_comment_leaves_the_code_on_both_sides():
    assert lints.c_lines("a /* c */ b\n") == [(1, "a b")]


def test_a_char_literal_holding_a_slash_is_not_a_comment():
    assert lints.c_lines("if (c == '/') { n++; }\n") == [(1, "if (c == '/') { n++; }")]


if __name__ == "__main__":
    for answer in ANSWER_CASES:
        test_the_lint_answer_to_one_input(*answer.values)
    for caught in CAUGHT_CASES:
        test_a_refused_run_names_the_lines_it_refused(*caught.values)
    test_a_function_name_outside_the_convention_is_caught()
    test_module_verb_and_sub_08xxxxxx_names_are_not_caught()
    test_a_c_source_the_build_skips_and_does_not_mark_is_caught()
    test_a_c_source_the_build_skips_and_marks_is_not_caught()
    test_a_c_source_the_build_compiles_and_marks_is_caught()
    test_a_c_source_the_build_compiles_and_does_not_mark_is_not_caught()
    test_a_marker_below_the_header_does_not_satisfy_the_check()
    test_a_tracked_rom_path_is_caught()
    test_a_tracked_source_path_is_not_caught()
    test_the_tracked_retail_hash_file_is_not_caught()
    test_a_tracked_file_over_a_megabyte_outside_assets_is_caught()
    test_a_tracked_file_over_a_megabyte_under_assets_is_not_caught()
    test_the_stale_readme_progress_line_is_caught()
    test_a_one_digit_percentage_change_is_caught()
    test_a_one_digit_byte_count_change_is_caught()
    test_the_measured_readme_progress_line_is_not_caught()
    test_a_readme_with_the_bytes_first_is_not_caught()
    test_a_second_percentage_is_caught()
    test_a_progress_line_without_its_command_is_caught()
    test_an_incbin_call_naming_a_slice_no_source_incbins_is_caught()
    test_an_incbin_call_naming_a_slice_the_source_incbins_is_not_caught()
    test_the_repository_has_no_lint_finding()
    test_a_pair_named_in_the_allowlist_is_cleared()
    test_a_multiline_c_comment_keeps_the_reported_line_numbers()
    test_a_line_comment_marker_inside_a_string_is_not_a_comment()
    test_a_block_comment_marker_inside_a_string_hides_nothing()
    test_an_inline_block_comment_leaves_the_code_on_both_sides()
    test_a_char_literal_holding_a_slash_is_not_a_comment()
    test_a_name_keyed_on_an_address_the_split_does_not_prove_is_caught()
    test_a_name_outside_module_verb_is_caught()
    test_a_repeated_name_is_caught()
    test_a_name_without_a_ledger_row_is_caught()
    test_a_ledger_row_that_disagrees_with_the_table_is_caught()
    test_a_ledger_row_without_an_evidence_cell_is_caught()
    test_a_table_that_matches_the_ledger_and_the_entries_is_not_caught()
    test_an_address_named_count_above_the_baseline_is_caught()
    test_an_address_named_count_below_an_unlowered_baseline_is_caught()
    test_an_address_named_count_matching_the_baseline_is_not_caught()
    test_a_baseline_that_carries_no_count_is_caught()
    test_readme_function_figures_that_match_the_tree_are_not_caught()
    test_the_function_figure_is_held_in_both_directions()
    test_a_readme_without_the_function_figure_is_caught()
    print("PASS test_lint")
