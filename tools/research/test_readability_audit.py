from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools"))

import readability_audit


def test_a_hardware_literal_is_counted_apart_from_a_ram_one():
    found = {0x040000D4: 2, 0x03000000: 1, 0x08000100: 4}
    assert readability_audit.within(found, *readability_audit.HARDWARE) == (2, 1)
    assert readability_audit.within(found, *readability_audit.RAM) == (1, 1)


def test_a_test_name_that_names_an_address_is_recognised():
    assert readability_audit.ADDRESS_IN_NAME.search("test_0801f08c_allocates") is not None
    assert readability_audit.ADDRESS_IN_NAME.search("test_rect_overlaps") is None


def test_the_audit_reports_every_class_it_promises():
    found = readability_audit.counts()
    for key in ("asm_files", "functions", "named_functions", "hardware_literals",
                "ram_literals", "raw_slices", "table_families", "dead_definitions", "tests"):
        assert key in found
    assert found["named_functions"] <= found["functions"]


def test_every_named_table_family_quotes_a_tracked_page():
    rows = readability_audit.table_families()
    assert rows
    assert len(set(row[0] for row in rows)) == len(rows)
    for family, _reader, evidence_class, cell in rows:
        path, evidence = cell.split(" ", 1)
        with open(os.path.join(readability_audit.ROOT, path), encoding="utf-8") as handle:
            page = handle.read()
        assert evidence_class == "decoded-format", family
        assert [token for token in re.findall(r"0x[0-9A-Fa-f]+", evidence)
                if token in page], family
