from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import format_reuse
import testkit


def test_the_tracked_format_page_check_passes():
    root = os.path.dirname(os.path.dirname(HERE))
    testkit.rom_bytes(os.path.join(root, "baserom.gba"), digest=format_reuse.ROM_SHA256)
    assert format_reuse.main(["--check"]) == 0


def test_the_tracked_format_page_is_present():
    assert os.path.exists(format_reuse.DOC)
