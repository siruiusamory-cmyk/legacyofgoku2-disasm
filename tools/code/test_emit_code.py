from __future__ import annotations

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)

import emit_code
import name_table
import testkit

_CACHE = {}


def result():
    if "result" not in _CACHE:
        rom = testkit.rom_bytes(emit_code.ROM, size=emit_code.END)
        _CACHE["result"] = emit_code.fragments(rom)
        _CACHE["rom"] = rom
    return _CACHE["result"], _CACHE["rom"]


def toolchain():
    home = os.environ.get("ADS12_HOME") or os.environ.get("ARMHOME")
    if not home:
        pytest.skip("no ADS 1.2 environment is active, so the reassembly check cannot run")
    return tuple(os.path.join(home, "Bin", name)
                 for name in ("armasm.exe", "armlink.exe", "fromelf.exe"))


def test_a_thumb_encoding_decodes_to_one_text_form():
    rom = bytearray(16)
    for index, half in enumerate((0x3005, 0x1C48, 0x8908, 0xB503, 0xB100, 0x4608)):
        rom[index * 2:index * 2 + 2] = half.to_bytes(2, "little")
    assert emit_code.decode(rom, emit_code.ROM_BASE, "thumb") == ("ADD", "r0, #0x5", 2)
    assert emit_code.decode(rom, emit_code.ROM_BASE + 2, "thumb") == ("ADD", "r0, r1, #0x1", 2)
    assert emit_code.decode(rom, emit_code.ROM_BASE + 4, "thumb") == ("LDRH", "r0, [r1, #0x8]", 2)
    assert emit_code.decode(rom, emit_code.ROM_BASE + 6, "thumb") == ("PUSH", "{r0, r1, lr}", 2)
    assert emit_code.decode(rom, emit_code.ROM_BASE + 8, "thumb") is None
    assert emit_code.decode(rom, emit_code.ROM_BASE + 10, "thumb") is None


def test_every_emitted_row_decodes():
    measured, _rom = result()
    causes = {}
    for _begin, size, cause in measured["raw"]:
        causes[cause] = causes.get(cause, 0) + size
    assert sorted(causes) == ["already carried before the remainder", "inside a carried container",
                              "outside the remainder"]
    assert measured["bytes"]["proven"] > 0
    assert measured["pool_bytes"] > 0
    assert measured["pools"]


def test_the_emitted_text_reassembles_to_the_image(tmp_path):
    measured, rom = result()
    armasm, armlink, fromelf = toolchain()
    for path in (armasm, armlink, fromelf):
        testkit.require(path, "%s is absent, so the reassembly check cannot run" % path)
    spans = emit_code.span_files(measured)
    for name, text in measured["files"].items():
        (tmp_path / name).write_text(text, encoding="utf-8", newline="\n")
    lines = ["\tAREA\tRemainder, CODE, READONLY"]
    position = emit_code.ROM_BASE + emit_code.START
    for begin, end, name in spans:
        if begin > position:
            lines.append("\t\tSPACE\t%d" % (begin - position))
        lines.append("\t\tINCLUDE\t%s" % (tmp_path / name))
        position = end
    source = tmp_path / "code.s"
    source.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    scatter = tmp_path / "code.ld"
    scatter.write_text("ROM_LOAD 0x08000000 {\n\tROM_REMAINDER 0x08000100\n\t{\n"
                       "\t\tcode.o (Remainder)\n\t}\n}\n", encoding="utf-8", newline="\n")
    for argv in ([armasm, str(source), "-o", str(tmp_path / "code.o")],
                 [armlink, str(tmp_path / "code.o"), "-noremove", "-scatter", str(scatter),
                  "-o", str(tmp_path / "code.axf")],
                 [fromelf, str(tmp_path / "code.axf"), "-bin", "-o", str(tmp_path / "code.bin")]):
        completed = subprocess.run(argv, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    image = (tmp_path / "code.bin").read_bytes()
    wrong = []
    for begin, end, _name in spans:
        offset = begin - emit_code.ROM_BASE - emit_code.START
        if image[offset:offset + end - begin] != rom[begin - emit_code.ROM_BASE:end - emit_code.ROM_BASE]:
            wrong.append(begin)
    assert wrong == []


def test_a_name_in_the_table_is_emitted_for_its_entry():
    measured, _rom = result()
    text = "".join(measured["files"].values())
    names = name_table.names()
    assert names
    assert [name for name in names.values() if "|%s|" % name not in text] == []


def test_an_entry_outside_the_table_keeps_its_address_name():
    measured, _rom = result()
    text = "".join(measured["files"].values())
    names = name_table.names()
    starts = set()
    for begin, _end, _mode, _tag, lines in measured["kept"]:
        starts.add(begin)
        starts.update(position for position, _op, _operands in lines)
    unnamed = [address for address in name_table.emitted()
               if address not in names and address in starts]
    assert unnamed
    assert ["|sub_%08X|" % address for address in unnamed
            if "|sub_%08X|" % address not in text] == []


def test_write_then_check_agrees(tmp_path):
    measured, _rom = result()
    assert emit_code.main(["--write", "--out", str(tmp_path)]) == 0
    assert emit_code.main(["--check", "--out", str(tmp_path)]) == 0
    assert len(list(tmp_path.glob("*.s"))) == len(measured["files"])
