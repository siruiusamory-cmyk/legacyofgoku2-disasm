from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import testkit

import callers


def test_a_sites_are_counted_per_target_and_per_calling_function():
    pairs = [(0x10, 0x40), (0x10, 0x40), (0x20, 0x40), (0x20, 0x50)]
    assert callers.counted(pairs) == {0x40: (3, 2), 0x50: (1, 1)}


def test_a_leaf_callee_set_and_a_named_callee_set_are_told_apart():
    pairs = [(0x10, 0x40)]
    assert callers.kind(pairs, 0x20, {}) == "leaf"
    pairs = [(0x10, 0x30)]
    assert callers.kind(pairs, 0x10, {0x30: "Named_Action"}) == "named-callees"
    assert callers.kind(pairs, 0x10, {0x40: "Named_Action"}) == "stubbable-callees"


def test_a_single_bx_pc_body_is_reported_as_a_state_switch():
    rom = testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), size=0x800000)
    assert callers.switches_state(rom, 0x08021F30, {0x08021F30})
    assert not callers.switches_state(rom, 0x080063E0, {0x080063E0, 0x080063E2})


def test_the_ranking_reproduces_the_split_census_on_the_retail_image():
    rom = testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), size=0x800000)
    rows = callers.ranked(rom, {})
    found = dict((target, site_count) for target, site_count, _callers, _kind in rows)
    assert found[0x0801F08C] == 222
    assert found[0x0801FC9C] == 50
    assert found[0x0800793A] == 35
    assert len([row for row in rows if row[3] == "arm-veneer"]) > 0


def test_a_ram_word_is_ranked_by_its_references_and_a_named_one_is_left_out():
    found = {0x03000100: 3, 0x03000200: 3, 0x03000300: 1, 0x04000000: 9, 0x02020202: 1}
    assert callers.ram_ranked(found, {0x03000200: "Named_Word"}) == [
        (0x03000100, 3), (0x02020202, 1), (0x03000300, 1)]


def test_the_ram_ranking_puts_the_most_referenced_literal_first_on_the_retail_image():
    testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), size=0x800000)
    testkit.require(os.path.join(ROOT, "build", "code"),
                    "the generated code is absent, so run rebuild.cmd first")
    rows = callers.ram_ranking()
    counts = [count for _value, count in rows]
    assert counts == sorted(counts, reverse=True)
    assert rows[0] == (0x03001FA8, 9)
    assert not set(value for value, _count in rows) & set(callers.name_table.ram_names())
