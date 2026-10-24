from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mapcontainer"))

import container_census
import mapcontainer
import testkit

IMAGE = [None]
CHUNKS = [None]
REAL = [None]
NULL = [None]


def image():
    if IMAGE[0] is None:
        IMAGE[0] = testkit.rom_bytes(container_census.ROM, digest=container_census.ROM_SHA256)
    return IMAGE[0]


def chunks():
    if CHUNKS[0] is None:
        CHUNKS[0] = mapcontainer.chunk_pointers(image())
    return CHUNKS[0]


def real():
    if REAL[0] is None:
        REAL[0] = container_census.summarise(image(), chunks=chunks())
    return REAL[0]


def null():
    if NULL[0] is None:
        NULL[0] = container_census.summarise(container_census.permute(image()),
                                             chunks=chunks())
    return NULL[0]


def hit(offset, kind, packed, declared=1):
    return {"offset": offset, "kind": kind, "packed": packed, "declared": declared,
            "payload": declared, "shape": "other", "digest": "", "ok": True}


def test_a_stored_hit_over_a_recovered_chunk_is_rejected_and_the_chunk_taken():
    chunk = hit(0x108, 1, 0x20)
    stored = hit(0x100, 0, 0x20)
    other = hit(0x200, 0, 8)
    accepted, rejected, recovered = container_census.population(
        [stored, chunk, other], [chunk])
    assert [item["offset"] for item in accepted] == [0x108, 0x200]
    assert rejected == [stored]
    assert recovered == [chunk]


def test_a_stored_hit_with_no_recovered_chunk_over_it_stays_accepted():
    stored = hit(0x100, 0, 0x20)
    accepted, rejected, recovered = container_census.population([stored], [])
    assert [item["offset"] for item in accepted] == [0x100]
    assert rejected == [] and recovered == []


def test_the_accepted_extents_do_not_overlap():
    extents = [(item["offset"], item["offset"] + item["packed"])
               for item in real()["accepted"]]
    assert extents == sorted(extents)
    assert all(first[1] <= second[0] for first, second in zip(extents, extents[1:]))


def test_the_tracked_census_page_and_ledger_check_pass():
    assert container_census.check_files(real(), null()) == 0


def test_the_census_and_the_null_are_pinned():
    result = real()
    assert len(result["accepted"]) == container_census.PINNED["accepted"]
    assert len(result["packed"]) == container_census.PINNED["packed"]
    assert len(result["stored"]) == container_census.PINNED["stored"]
    assert result["union_bytes"] == container_census.PINNED["union_bytes"]
    assert result["stored_over"] == container_census.PINNED["rejected"]
    assert result["raised"] == container_census.PINNED["recovered"]
    permuted = null()
    assert len(permuted["accepted"]) == container_census.PINNED["null_accepted"]
    assert len(permuted["packed"]) == container_census.PINNED["null_packed"]
