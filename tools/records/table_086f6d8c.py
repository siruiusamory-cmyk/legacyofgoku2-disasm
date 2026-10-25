from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "maprecords"))

import maprecords

ROM = os.path.join(ROOT, "baserom.gba")
BUILD = os.path.join(ROOT, "build", "records")
ROM_BASE = 0x08000000
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
CENSUS_BYTES = 4288
TABLE = 0x086F6D8C
HEADER = 8

SPECS = {
    "table": [("count_00", 0x00, 4, "u32"), ("records_04", 0x04, 4, "ref")],
    "array": [("records", 0x00, 4, "refs")],
    "record": [("reserved_00_13", 0x00, 0x14, "bytes"), ("count_14", 0x14, 4, "u32"),
               ("pointers_18", 0x18, 4, "refs")],
    "entry": [("key_00", 0x00, 1, "u8"), ("key_01", 0x01, 1, "u8"),
              ("flag_02", 0x02, 2, "u16")],
}
PINNED = {"table": 1, "array": 1, "record": 68, "entry": 297}
ENTRY_WIDTH = 4


def u32(image, offset):
    return int.from_bytes(image[offset:offset + 4], "little")


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def label(family, index):
    return "%s_%03d" % (family, index)


def walk(image):
    count = u32(image, TABLE - ROM_BASE)
    array = u32(image, TABLE - ROM_BASE + 4)
    if not 0 < count <= 0x1000 or not in_image(image, array):
        raise ValueError("the table header at %08x holds count %d and array %08x"
                         % (TABLE, count, array))
    array -= ROM_BASE
    if array + 4 * count > len(image):
        raise ValueError("the record array at %08x runs past the image" % (array + ROM_BASE))
    records, entries, seen = [], {}, set()
    for index in range(count):
        address = u32(image, array + 4 * index)
        if not in_image(image, address) or address & 3:
            raise ValueError("record %d is at %08x, not a word in the image" % (index, address))
        record = address - ROM_BASE
        if record in seen:
            raise ValueError("record %d repeats the record at %08x" % (index, address))
        seen.add(record)
        pointers = u32(image, record + 0x14)
        if pointers > 0x100 or record + 0x18 + 4 * pointers > len(image):
            raise ValueError("record %d holds %d pointers" % (index, pointers))
        records.append((record, 0x18 + 4 * pointers))
        for slot in range(pointers):
            address = u32(image, record + 0x18 + 4 * slot)
            if not in_image(image, address) or address & 3:
                raise ValueError("record %d slot %d names %08x" % (index, slot, address))
            entries.setdefault(address - ROM_BASE, ENTRY_WIDTH)
    for record, width in records:
        for entry in entries:
            if record < entry + ENTRY_WIDTH and entry < record + width:
                raise ValueError("the entry at %08x overlaps a record" % (entry + ROM_BASE))
    return {"table": [(TABLE - ROM_BASE, HEADER)], "array": [(array, 4 * count)],
            "record": records, "entry": list(entries.items())}


def tables(directory=None):
    return maprecords.load_tables(PINNED, SPECS, directory or HERE)


def build_records(rows, found, gaps=None):
    return maprecords.build_records(rows, maprecords.container_extents() if gaps is None else gaps,
                                    found, SPECS, PINNED)


def tokens(image, rows=None):
    return [(begin, end, "build\\records\\rec_%x_%x.bin" % (begin, end))
            for begin, end in maprecords.runs(build_records(rows or tables(), walk(image)))]


def write(image, rows=None):
    return maprecords.write_runs(build_records(rows or tables(), walk(image)), BUILD, "rec")


def check(image, rows=None):
    return maprecords.check_records(build_records(rows or tables(), walk(image)), image)


def extract(image):
    found = walk(image)
    entries = {"%08x" % (offset + ROM_BASE): label("entry", index)
               for index, (offset, _width) in enumerate(found["entry"])}
    rows = {family: [] for family in PINNED}
    rows["table"].append({"label": "table", "address": "%08x" % TABLE,
                          "count_00": "%08x" % len(found["record"]), "records_04": "array_000"})
    rows["array"].append({"label": "array_000",
                          "address": "%08x" % (found["array"][0][0] + ROM_BASE),
                          "records": " ".join(label("record", index)
                                              for index in range(len(found["record"])))})
    for index, (offset, _width) in enumerate(found["record"]):
        pointers = u32(image, offset + 0x14)
        slots = ["%08x" % u32(image, offset + 0x18 + 4 * slot) for slot in range(pointers)]
        rows["record"].append(
            {"label": label("record", index), "address": "%08x" % (offset + ROM_BASE),
             "reserved_00_13": maprecords.hexed(image, offset, 0x14),
             "count_14": "%08x" % pointers,
             "pointers_18": " ".join(entries.get(slot, slot) for slot in slots)})
    for index, (offset, _width) in enumerate(found["entry"]):
        rows["entry"].append({"label": label("entry", index),
                              "address": "%08x" % (offset + ROM_BASE),
                              "key_00": "%02x" % image[offset], "key_01": "%02x" % image[offset + 1],
                              "flag_02": "%04x" % int.from_bytes(image[offset + 2:offset + 4],
                                                                "little")})
    return rows


def uncited_fields(text):
    return maprecords.uncited_fields(text, SPECS)


def write_tables(tables, directory=None):
    maprecords.write_tables(tables, SPECS, directory or HERE)


def read_rom():
    return maprecords.read_rom(ROM, ROM_SHA256)


def spans_of(found):
    spans = []
    for family in PINNED:
        spans += [(offset, offset + width) for offset, width in found[family]]
    return spans


def null(image):
    found = walk(image)
    other = maprecords.permuted(image, spans_of(found))
    try:
        counts = {family: len(other_rows) for family, other_rows in walk(other).items()}
    except ValueError:
        return {family: 0 for family in PINNED}
    return counts


def differing(image, rows=None):
    rows = rows or tables()
    found = walk(image)
    labels = maprecords.labels_of(rows)
    other = maprecords.permuted(image, spans_of(found))
    out = {}
    for family, family_rows in rows.items():
        if len(found[family]) != len(family_rows):
            raise ValueError("%s holds %d row(s) for %d record(s)"
                             % (family, len(family_rows), len(found[family])))
        out[family] = sum(1 for (offset, width), row in zip(found[family], family_rows)
                          if other[offset:offset + width]
                          != maprecords.encode_row(family, row, labels, SPECS))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--null"]:
        image = read_rom()
        result = null(image)
        print("permuted " + " ".join("%s=%d" % (family, result[family]) for family in PINNED))
        differ = differing(image)
        print("differing records " + " ".join("%s=%d" % (family, differ[family])
                                              for family in PINNED))
        return 0 if not any(result.values()) and all(differ.values()) else 1
    return maprecords.generator_main(sys.modules[__name__], "table_086f6d8c", argv)


if __name__ == "__main__":
    raise SystemExit(main())
