from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import container_census
import testkit


def test_the_tracked_census_page_and_ledger_check_pass():
    testkit.rom_bytes(container_census.ROM, digest=container_census.ROM_SHA256)
    assert container_census.main(["--check"]) == 0


def test_the_census_and_the_null_are_pinned():
    image = testkit.rom_bytes(container_census.ROM, digest=container_census.ROM_SHA256)
    real = container_census.summarise(image)
    assert len(real["accepted"]) == container_census.PINNED["accepted"]
    assert len(real["packed"]) == container_census.PINNED["packed"]
    assert len(real["stored"]) == container_census.PINNED["stored"]
    assert real["union_bytes"] == container_census.PINNED["union_bytes"]
    null = container_census.summarise(container_census.permute(image))
    assert len(null["accepted"]) == container_census.PINNED["null_accepted"]
    assert len(null["packed"]) == container_census.PINNED["null_packed"]
