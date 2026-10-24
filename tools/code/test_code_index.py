from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import code_index
import testkit


@pytest.fixture(scope="module")
def tree():
    rom = testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), size=0x800000)
    found = code_index.spans(rom)
    return code_index.text(rom, found), found


def test_a_span_is_found_by_the_address_it_holds():
    found = [(0x100, 0x110, "a.s"), (0x110, 0x120, "b.s")]
    assert code_index.file_of(found, 0x100) == "a.s"
    assert code_index.file_of(found, 0x11F) == "b.s"
    assert code_index.file_of(found, 0x120) is None


def test_the_index_names_a_known_function_and_its_file(tree):
    rendered = tree[0]
    assert "| `Blend_ShowBg0` | `0x080003ea` | `Blend_ShowBg0.s` |" in rendered
    assert "| `Heap_Alloc` | `0x0801f08c` | `Heap_Alloc.s` |" in rendered
    assert "| `Display_SetControlBit` | `0x08006298` | `Display_SetControlBit.s` |" in rendered


def test_every_function_start_has_its_own_row_and_a_file_unless_the_emitter_does_not_write_it(tree):
    rendered, found = tree
    starts = code_index.name_table.starts()
    assert len(starts) == len([1 for line in rendered.splitlines()
                               if line.startswith("| `") and not line.startswith("| `---")])
    assert [address for address in starts
            if "| `0x%08x` | `none` |" % address in rendered] == [
                address for address in starts if code_index.file_of(found, address) is None]


def test_the_tracked_index_is_what_the_tree_derives():
    assert code_index.main(["--check"]) == 0
