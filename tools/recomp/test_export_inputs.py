from __future__ import annotations

import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools", "split"))

import export_inputs


def blocks(text, name):
    out = []
    current = None
    for line in text.splitlines():
        if line == "[[%s]]" % name:
            current = {}
            out.append(current)
            continue
        if line.startswith("["):
            current = None
            continue
        if current is not None and " = " in line:
            key, value = line.split(" = ", 1)
            current[key] = value.strip('"')
    return out


def counts_of(text):
    out = {}
    lines = text.splitlines()
    for line in lines[lines.index("[counts]") + 1:]:
        if not line:
            break
        key, value = line.split(" = ")
        if value.isdigit():
            out[key] = int(value)
    return out


def test_a_reset_vector_that_is_not_a_branch_is_refused():
    rom = bytearray(0x200)
    struct.pack_into("<I", rom, 0, 0xE12FFF1E)
    with pytest.raises(SystemExit):
        export_inputs.entry_address(bytes(rom))


def test_a_missing_image_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        export_inputs.identity(str(tmp_path / "absent.gba"), str(tmp_path / "absent.sha1"))


def test_a_digest_that_is_not_the_recorded_sha1_is_refused(tmp_path):
    image = tmp_path / "baserom.gba"
    image.write_bytes(b"\x00" * 16)
    sha1 = tmp_path / "baserom.sha1"
    sha1.write_text("0" * 40 + "\n", encoding="ascii")
    with pytest.raises(SystemExit):
        export_inputs.identity(str(image), str(sha1))


def test_the_tracked_export_check_passes():
    if not os.path.exists(export_inputs.ROM):
        pytest.skip("baserom.gba is absent, so this check cannot run")
    assert export_inputs.main(["--check"]) == 0


def test_the_export_counts_are_the_extents_it_carries():
    if not os.path.exists(export_inputs.ROM):
        pytest.skip("baserom.gba is absent, so this check cannot run")
    text = export_inputs.render()
    counts = counts_of(text)
    code = blocks(text, "code")
    entries = blocks(text, "entry")
    copies = blocks(text, "code_copy")
    tables = blocks(text, "jump_table")
    assert counts["functions"] == len(code)
    assert counts["code_bytes"] == sum(int(row["size"]) for row in code)
    assert counts["entries"] == len(entries)
    assert counts["code_copies"] == len(copies) == 1
    assert counts["jump_tables"] == len(tables)
    assert copies[0] == {"runtime_start": "0x03000000",
                         "source_start": "0x087fd6bc", "size": "0xe7c"}
    assert tables[0]["base"] == "0x0800b274"
    assert tables[0]["entries"] == "14"
    assert {row["origin"] for row in code} == set(export_inputs.CLASS_TAGS.values())
    assert {row["mode"] for row in code} == {"thumb", "arm"}
    assert [row["addr"] for row in entries] == sorted(row["addr"] for row in entries)
    import code_split
    totals = code_split.read_totals()
    assert counts["code_bytes"] == (totals["proven code"]
                                    + totals["filtered pointer-entry code"]
                                    + totals["table-held code"]
                                    + totals["gap-fill code"])


def test_every_code_class_is_exported_with_its_own_tag():
    if not os.path.exists(export_inputs.ROM):
        pytest.skip("baserom.gba is absent, so this check cannot run")
    code = blocks(export_inputs.render(), "code")
    import code_split
    totals = code_split.read_totals()
    for name, tag in export_inputs.CLASS_TAGS.items():
        assert sum(int(row["size"]) for row in code if row["origin"] == tag) == totals[name]


def test_the_export_places_the_interrupt_handler_inside_the_code_copy():
    if not os.path.exists(export_inputs.ROM):
        pytest.skip("baserom.gba is absent, so this check cannot run")
    text = export_inputs.render()
    fields = {}
    inside = False
    for line in text.splitlines():
        if line == "[irq]":
            inside = True
            continue
        if inside:
            if not line or line.startswith("["):
                break
            key, value = line.split(" = ")
            fields[key] = value
    copy = blocks(text, "code_copy")[0]
    start = int(copy["runtime_start"], 16)
    assert fields["vector"] == "0x03007ffc"
    assert fields["handler"] == "0x03000824"
    assert start <= int(fields["handler"], 16) < start + int(copy["size"], 16)


if __name__ == "__main__":
    print("PASS test_export_inputs")
