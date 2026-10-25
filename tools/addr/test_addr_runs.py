from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import addr_runs
import testkit

ROOT = os.path.dirname(os.path.dirname(HERE))


def retail():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), digest=addr_runs.ROM_SHA256)


def test_the_table_reproduces_the_retail_bytes():
    result = addr_runs.check(retail())
    assert result["mismatched_records"] == 0
    assert result["records"] == addr_runs.PINNED["run"]


def test_the_table_accounts_for_the_labelled_run_class_exactly():
    result = addr_runs.check(retail())
    assert result["emitted_bytes"] == addr_runs.CENSUS_BYTES == 7892


def test_the_emitted_runs_are_inside_the_image_and_do_not_overlap():
    image = retail()
    previous, total = 0, 0
    for start, end, _token in addr_runs.tokens(image):
        assert 0x100 <= start < end <= 0x800000
        assert start >= previous
        previous = end
        total += end - start
    assert total == addr_runs.CENSUS_BYTES


def test_every_word_is_a_code_label_the_emitter_writes():
    rows = addr_runs.tables()
    labels = addr_runs.labels_map(retail())
    words = 0
    for row in rows["run"]:
        tokens = row["words"].split()
        assert len(tokens) >= 2
        for token in tokens:
            name, _, odd = token.partition("+")
            assert name in labels
            assert odd in ("", "1")
            words += 1
    assert words == addr_runs.CENSUS_BYTES // 4


def test_a_doctored_reference_changes_the_word_it_encodes():
    rows = addr_runs.tables()
    labels = addr_runs.labels_map(retail())
    row = rows["run"][0]
    before = addr_runs.encode_row("run", row, labels)
    first = row["words"].split()[0]
    name, _, odd = first.partition("+")
    doctored = dict(row)
    doctored["words"] = " ".join([name if odd else name + "+1"]
                                 + row["words"].split()[1:])
    after = addr_runs.encode_row("run", doctored, labels)
    assert before != after and before[4:] == after[4:]


def test_the_permuted_runs_resolve_to_nothing():
    image = retail()
    assert addr_runs.null(image) == {"run": 0}
    assert addr_runs.differing(image) == {"run": addr_runs.PINNED["run"]}


def test_the_check_refuses_a_doctored_table():
    image = retail()
    rows = addr_runs.tables()
    tokens = rows["run"][0]["words"].split()
    name, _, odd = tokens[0].partition("+")
    doctored = dict(rows["run"][0])
    doctored["words"] = " ".join([name if odd else name + "+1"] + tokens[1:])
    rows["run"][0] = doctored
    result = addr_runs.check(image, rows=rows)
    assert result["mismatched_records"] == 1
