from __future__ import annotations

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "maprecords"))
sys.path.insert(0, os.path.join(ROOT, "tools", "research"))

import maprecords
import opcode_stream

ROM = os.path.join(ROOT, "baserom.gba")
BUILD = os.path.join(ROOT, "build", "opcode")
ROM_BASE = 0x08000000
ROM_SHA256 = opcode_stream.ROM_SHA256
CENSUS_BYTES = 1227
SPLIT = os.path.join(ROOT, "tools", "split", "CODE_SPLIT.csv")

SPECS = {
    "quest_record": [("reserved_00_03", 0x00, 4, "bytes"), ("stream_04", 0x04, 4, "u32"),
               ("stream_08", 0x08, 4, "u32"), ("text_0c", 0x0C, 4, "u32")],
    "instruction": [("opcode", 0x00, 1, "u8"), ("operands", 0x01, 0, "bytes")],
}
PINNED = {"quest_record": 43, "instruction": 323}


def kind_of(opcode):
    return "none" if opcode == opcode_stream.END else opcode_stream.HANDLERS[opcode][1]


def u32(image, offset):
    return int.from_bytes(image[offset:offset + 4], "little")


def label(index, slot):
    return "instruction_%03d_%03d" % (index, slot)


def streams(image):
    return [(record, 0x10, addresses)
            for record, addresses in opcode_stream.streams(image)]


def instructions(image):
    out = []
    for index, row in enumerate(opcode_stream.census(image)):
        if row["problem"] is not None:
            raise ValueError("the stream at %08x does not decode: %s"
                             % (row["start"] + ROM_BASE, row["problem"]))
        items = row["instructions"]
        for slot, item in enumerate(items):
            stop = items[slot + 1][0] if slot + 1 < len(items) else row["stop"]
            out.append((index, slot, item, stop - item[0]))
    return out


def holes():
    return maprecords.container_extents()


def walk(image):
    records = [(record, width) for record, width, _addresses in streams(image)]
    places = [(item[0], width) for _index, _slot, item, width in instructions(image)]
    return {"quest_record": records, "instruction": places}


def encode_row(family, row, labels, specs=None):
    if family == "quest_record":
        return maprecords.encode_row(family, row, labels, SPECS)
    if family != "instruction":
        raise ValueError("%s is not a family of this table" % family)
    opcode = row[1]
    kind = kind_of(opcode)
    out = bytearray([opcode])
    if kind == "none":
        if row[2]:
            raise ValueError("opcode %#04x carries %s" % (opcode, row[2]))
        return bytes(out)
    if kind in ("byte", "dispatch", "jump", "skip", "loop"):
        if len(row[2]) != 1:
            raise ValueError("opcode %#04x carries %r" % (opcode, row[2]))
        return bytes(out) + row[2]
    if kind == "varint":
        return bytes(out) + opcode_stream.varint_bytes(row[3])
    if kind == "counted":
        out.append(row[3])
        for value in row[4]:
            out += opcode_stream.varint_bytes(value)
        return bytes(out)
    raise ValueError("opcode %#04x has kind %s" % (opcode, kind))


def tokens_of_operands(opcode, tokens):
    kind = kind_of(opcode)
    if kind == "none":
        return b""
    if kind in ("byte", "dispatch", "jump", "skip", "loop"):
        return b"".join(bytes.fromhex(token) for token in tokens)
    if kind == "varint":
        return opcode_stream.varint_bytes(int(tokens[0][1:], 16))
    if kind == "counted":
        out = bytearray([int(tokens[0][1:], 16)])
        for token in tokens[1:]:
            out += opcode_stream.varint_bytes(int(token[1:], 16))
        return bytes(out)
    raise ValueError("opcode %#04x has kind %s" % (opcode, kind))


def tables(directory=None):
    return maprecords.load_tables(PINNED, SPECS, directory or HERE)


def stream_item(image, row):
    index, slot = [int(part) for part in row["label"].split("_")[1:]]
    opcode = int(row["opcode"], 16)
    item = (int(row["address"], 16) - ROM_BASE, opcode,
            tokens_of_operands(opcode, row["operands"].split()))
    kind = kind_of(opcode)
    tokens = row["operands"].split()
    if kind == "varint":
        item += (int(tokens[0][1:], 16),)
    elif kind == "counted":
        item += (int(tokens[0][1:], 16), [int(token[1:], 16) for token in tokens[1:]])
    return index, slot, item


def build_records(rows, found, gaps=None):
    holes_now = holes() if gaps is None else gaps
    labels = {row["label"]: int(row["address"], 16) - ROM_BASE
              for family in rows for row in rows[family]}
    for family in PINNED:
        if len(rows[family]) != len(found[family]):
            raise ValueError("%s holds %d row(s) for %d record(s)"
                             % (family, len(rows[family]), len(found[family])))
    out = []
    for row, (offset, width) in zip(rows["quest_record"], found["quest_record"]):
        if int(row["address"], 16) - ROM_BASE != offset:
            raise ValueError("%s names 0x%s, not 0x%X"
                             % (row["label"], row["address"], offset + ROM_BASE))
        data = encode_row("quest_record", row, labels)
        if len(data) != width:
            raise ValueError("%s encodes %d B, not %d" % (row["label"], len(data), width))
        out.append((offset, data, maprecords.uncovered(offset, len(data), holes_now)))
    for row, (offset, width) in zip(rows["instruction"], found["instruction"]):
        if int(row["address"], 16) - ROM_BASE != offset:
            raise ValueError("%s names 0x%s, not 0x%X"
                             % (row["label"], row["address"], offset + ROM_BASE))
        data = encode_row("instruction", stream_item(None, row)[2], labels)
        if len(data) != width:
            raise ValueError("%s encodes %d B, not %d" % (row["label"], len(data), width))
        out.append((offset, data, maprecords.uncovered(offset, len(data), holes_now)))
    return sorted(out)


def tokens(image, rows=None):
    return [(begin, end, "build\\opcode\\rec_%x_%x.bin" % (begin, end))
            for begin, end in maprecords.runs(build_records(rows or tables(), walk(image)))]


def write(image, rows=None):
    return maprecords.write_runs(build_records(rows or tables(), walk(image)), BUILD, "rec")


def check(image, rows=None):
    return maprecords.check_records(build_records(rows or tables(), walk(image)), image)


def operand_tokens(item):
    kind = kind_of(item[1])
    if kind == "none":
        return []
    if kind in ("byte", "dispatch", "jump", "skip", "loop"):
        return ["%02x" % byte for byte in item[2]]
    if kind == "varint":
        return ["v%x" % item[3]]
    if kind == "counted":
        return ["c%x" % item[3]] + ["v%x" % value for value in item[4]]
    raise ValueError("opcode %#04x has kind %s" % (item[1], kind))


def extract(image):
    rows = {family: [] for family in PINNED}
    for index, (record, _width, addresses) in enumerate(streams(image)):
        rows["quest_record"].append(
            {"label": "record_%03d" % index, "address": "%08x" % (record + ROM_BASE),
             "reserved_00_03": maprecords.hexed(image, record, 4),
             "stream_04": "%08x" % addresses[0], "stream_08": "%08x" % addresses[1],
             "text_0c": "%08x" % u32(image, record + 0x0C)})
    for index, slot, item, _width in instructions(image):
        rows["instruction"].append(
            {"label": label(index, slot), "address": "%08x" % (item[0] + ROM_BASE),
             "opcode": "%02x" % item[1], "operands": " ".join(operand_tokens(item))})
    return rows


def uncited_fields(text):
    return maprecords.uncited_fields(text, SPECS)


def write_tables(tables, directory=None):
    maprecords.write_tables(tables, SPECS, directory or HERE)


def read_rom():
    return opcode_stream.read_rom(ROM)


def spans_of(found):
    return [(offset, offset + width) for family in PINNED for offset, width in found[family]]


def null(image):
    try:
        found = walk(image)
        return {family: len(rows) for family, rows in walk(maprecords.permuted(
            image, spans_of(found))).items()}
    except (ValueError, KeyError):
        return {family: 0 for family in PINNED}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--null"]:
        result = null(read_rom())
        print("permuted " + " ".join("%s=%d" % (family, result[family]) for family in PINNED))
        return 0 if not any(result.values()) else 1
    return maprecords.generator_main(sys.modules[__name__], "opcode_rows", argv)


if __name__ == "__main__":
    raise SystemExit(main())
