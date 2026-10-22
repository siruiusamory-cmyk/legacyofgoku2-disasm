from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import asset_directory
import testkit


def test_the_directory_entry_resolves_to_a_container():
    image = testkit.rom_bytes(asset_directory.ROM, digest=asset_directory.ROM_SHA256)
    result = asset_directory.measure(image)
    assert result["entries"] == asset_directory.TABLE_ENTRIES
    assert result["definition"] == 0x08242DBC
    assert result["slots"] == 8
    assert result["containers"] == 6
    assert result["declared"] == [4096]
    assert result["kind"] == 1
    assert result["piece_box"] == (-20, -56, 64, 64)
    assert result["piece_container"] == 0x082348D0
    assert result["payload"] == 4096
