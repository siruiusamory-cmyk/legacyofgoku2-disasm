from __future__ import annotations

import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "tools", "split"))

import export_inputs
import export_labels


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
    rows = export_inputs.bounds_rows()
    assert counts["functions"] == len(code) == len(rows)
    assert counts["code_bytes"] == sum(int(row["size"]) for row in code)
    assert counts["code_bytes"] == sum(row[1] for row in rows)
    assert counts["entries"] == len(entries)
    assert counts["code_copies"] == len(copies) == 1
    assert counts["jump_tables"] == len(tables)
    assert copies[0] == {"runtime_start": "0x03000000",
                         "source_start": "0x087fd6bc", "size": "0xe7c"}
    assert tables[0]["base"] == "0x0800b274"
    assert tables[0]["entries"] == "14"
    assert {row["origin"] for row in code} == {row[3] for row in rows}
    assert {row["mode"] for row in code} == {"thumb", "arm"}
    assert [row["addr"] for row in entries] == sorted(row["addr"] for row in entries)


def test_the_tracked_export_carries_every_census_row_with_its_extent():
    text = open(export_inputs.OUT, encoding="ascii", newline="").read()
    rows = export_inputs.bounds_rows()
    code = [(int(match.group(1), 16), int(match.group(3)), match.group(2))
            for match in export_inputs.CODE_ROW.finditer(text)]
    assert rows
    assert sorted(code) == sorted((start, size, mode) for start, size, mode, _origin
                                  in rows)
    assert export_inputs.audit(text, rows) == ([], [])


def test_a_census_row_with_no_code_row_is_reported():
    rows = [(0x08000100, 4, "thumb", "census")]
    uncovered, modeless = export_inputs.audit("", rows)
    assert uncovered == rows
    assert modeless == []
    assert export_inputs.audit('[[code]]\naddr = 0x08000100\nmode = ""\nsize = 4\n'
                               'origin = "census"\n', rows) == ([], [""])


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


def test_a_census_row_with_no_end_is_skipped(tmp_path):
    where = tmp_path / "tools" / "code"
    where.mkdir(parents=True)
    (where / "FUNCTION_ENDS.csv").write_text(
        "address,mode,origin,end,reason\n"
        "0x08000100,thumb,census,0x08000104,-\n"
        "0x08000200,thumb,census,-,no-body\n", encoding="ascii")
    assert export_inputs.bounds_rows(str(tmp_path)) == [
        (0x08000100, 4, "thumb", "census")]


def test_a_recorded_entry_reaches_the_runtime_set(tmp_path):
    where = tmp_path / "tools" / "recomp"
    where.mkdir(parents=True)
    (where / "RUNTIME_LABELS.csv").write_text(
        "region,address,mode\nrom,0x0800f00a,thumb\n", encoding="ascii")
    assert export_inputs.runtime_entries(tmp_path) == [
        (0x0800F00A, export_inputs.code_split.MODE_THUMB)]


def test_a_recorded_entry_with_an_unknown_mode_is_refused(tmp_path):
    where = tmp_path / "tools" / "recomp"
    where.mkdir(parents=True)
    (where / "RUNTIME_LABELS.csv").write_text(
        "region,address,mode\nrom,0x0800f00a,armx\n", encoding="ascii")
    with pytest.raises(SystemExit):
        export_inputs.runtime_entries(tmp_path)


def test_the_label_map_carries_an_end_only_for_a_code_row(tmp_path):
    inputs = tmp_path / "RECOMP_INPUTS.toml"
    inputs.write_text(
        '[counts]\nfunctions = 1\n\n[[code]]\naddr = 0x0800010a\nmode = "thumb"\n'
        'size = 4\norigin = "census"\n\n[[entry]]\naddr = 0x0800f00a\nmode = "thumb"\n',
        encoding="ascii")
    rom = tmp_path / "baserom.gba"
    rom.write_bytes(b"\x00" * 16)
    text = export_labels.labels_text(str(inputs), str(rom))
    assert "end = 0x0800010e" in text
    assert text.count("[[functions]]") == 2


if __name__ == "__main__":
    print("PASS test_export_inputs")
