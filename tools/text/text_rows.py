from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "maprecords"))
sys.path.insert(0, HERE)

import maprecords
import text_storage

ROM = os.path.join(ROOT, "baserom.gba")
BUILD = os.path.join(ROOT, "build", "text")
ROM_BASE = text_storage.ROM_BASE
ROM_SHA256 = text_storage.ROM_SHA256
CENSUS_BYTES = 20481
CONTAINER = text_storage.TEXT_CONTAINER

SPECS = {
    "roster": [("text_00", 0x00, 4, "ref"), ("text_04", 0x04, 4, "ref"),
               ("sprite_08", 0x08, 4, "u32"), ("reserved_0c_0f", 0x0C, 4, "bytes"),
               ("record_10", 0x10, 4, "u32")],
    "roster_string": [("text", 0x00, 0, "string")],
    "objective": [("text", 0x00, 0, "string")],
    "font": [("offset", 0x00, 2, "u16")],
}
PINNED = {"roster": 128, "roster_string": 124, "objective": 43, "font": 256}
COUNTS = {"roster": 128, "roster_string": 124, "objective": 43, "font": 221}


def u16(image, offset):
    return int.from_bytes(image[offset:offset + 2], "little")


def u32(image, offset):
    return int.from_bytes(image[offset:offset + 4], "little")


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def label(family, index):
    return "%s_%03d" % ("string" if family == "roster_string" else family, index)


def span(image, offset):
    end = offset
    while end < len(image) and image[end] != 0:
        if image[end] not in text_storage.PRINTABLE or end - offset >= text_storage.LIMIT:
            return None
        end += 1
    return end + 1 - offset if end < len(image) else None


def text_at(image, address):
    if not in_image(image, address):
        return None
    return span(image, address - ROM_BASE)


def roster_slots():
    return [(text_storage.ROSTER + text_storage.ROSTER_STRIDE * index,
             text_storage.ROSTER_STRIDE) for index in range(text_storage.ROSTER_RECORDS)]


def objective_slots():
    return [(text_storage.OBJECTIVES + text_storage.OBJECTIVE_STRIDE * index,
             text_storage.OBJECTIVE_STRIDE) for index in range(text_storage.OBJECTIVE_RECORDS)]


def font_slots():
    return [(text_storage.FONT_TABLE + 2 * code, 2)
            for code in range(text_storage.FONT_CODES)]


def font_codes(image):
    defined = [(code, u16(image, text_storage.FONT_TABLE + 2 * code))
               for code in range(text_storage.FONT_CODES)]
    defined = [pair for pair in defined if pair[1]]
    if not all(later[1] > earlier[1] for earlier, later in zip(defined, defined[1:])):
        return 0
    return len([pair for pair in defined
                if u16(image, text_storage.FONT_TABLE + 2 * pair[1])])


def walk(image):
    roster, strings, names = [], [], {}
    for offset, width in roster_slots():
        roster.append((offset, width))
        for field in text_storage.ROSTER_FIELDS:
            address = u32(image, offset + field)
            if address - ROM_BASE in names:
                continue
            length = text_at(image, address)
            if length is None:
                continue
            names[address - ROM_BASE] = label("roster_string", len(names))
            strings.append((address - ROM_BASE, length))
    objectives, task_names = [], {}
    for offset, _width in objective_slots():
        address = u32(image, offset + text_storage.OBJECTIVE_TEXT)
        length = text_at(image, address)
        if length is None:
            continue
        task_names.setdefault(address - ROM_BASE, label("objective", len(objectives)))
        objectives.append((address - ROM_BASE, length))
    return {"roster": roster, "roster_string": strings, "objective": objectives,
            "font": font_slots(), "names": names, "task_names": task_names}


def names_of(image, found):
    names = dict(found["names"])
    names.update(found["task_names"])
    return names


def counts(image):
    found = walk(image)
    both = [offset for offset, _width in roster_slots()
            if all(text_at(image, u32(image, offset + field)) is not None
                   for field in text_storage.ROSTER_FIELDS)]
    return {"roster": len(both), "roster_string": len(found["roster_string"]),
            "objective": len(found["objective"]), "font": font_codes(image)}


def tables(directory=None):
    return maprecords.load_tables(PINNED, SPECS, directory or HERE)


def holes():
    return [(begin, end) for begin, end in maprecords.container_extents() if begin != CONTAINER]


def build_records(rows, found, gaps=None):
    return maprecords.build_records(rows, holes() if gaps is None else gaps, found, SPECS,
                                    PINNED)


def tokens(image, rows=None):
    return [(begin, end, "build\\text\\rec_%x_%x.bin" % (begin, end))
            for begin, end in maprecords.runs(build_records(rows or tables(), walk(image)))]


def write(image, rows=None):
    return maprecords.write_runs(build_records(rows or tables(), walk(image)), BUILD, "rec")


def check(image, rows=None):
    records = build_records(rows or tables(), walk(image))
    mismatched = sum(1 for offset, data, _spans in records
                     if image[offset:offset + len(data)] != data)
    return {"records": len(records), "mismatched_records": mismatched,
            "bytes": sum(len(data) for _offset, data, _spans in records),
            "emitted_bytes": sum(stop - begin for _offset, _data, spans in records
                                 for begin, stop in spans)}


def spans_of(families, found):
    spans = []
    for family in families:
        if family == "roster":
            spans += roster_slots()
        elif family == "objective":
            spans += objective_slots() + found["objective"]
        elif family == "font":
            spans.append((text_storage.FONT_TABLE,
                          text_storage.FONT_TABLE + 2 * text_storage.FONT_CODES))
        else:
            spans += found[family]
    return [(offset, offset + width) for offset, width in spans]


def null(image, families=None):
    found = walk(image)
    return counts(maprecords.permuted(image, spans_of(families or PINNED, found)))


def differing(image, rows=None):
    rows = rows or tables()
    found = walk(image)
    labels = maprecords.labels_of(rows)
    other = maprecords.permuted(image, spans_of(tuple(PINNED), found))
    out = {}
    for family, family_rows in rows.items():
        if len(found[family]) != len(family_rows):
            raise ValueError("%s holds %d row(s) for %d record(s)"
                             % (family, len(family_rows), len(found[family])))
        out[family] = sum(1 for offset, row in zip(found[family], family_rows)
                          if other[offset[0]:offset[0] + offset[1]]
                          != maprecords.encode_row(family, row, labels, SPECS))
    return out


def write_tables(tables, directory=None):
    maprecords.write_tables(tables, SPECS, directory or HERE)


def text_content(image, offset, width):
    return image[offset:offset + width - 1].decode("ascii")


def extract(image):
    found = walk(image)
    names = names_of(image, found)
    rows = {family: [] for family in PINNED}
    for index, (offset, _width) in enumerate(found["roster"]):
        rows["roster"].append(
            {"label": label("roster", index), "address": "%08x" % (offset + ROM_BASE),
             "text_00": maprecords.reference(image, names, u32(image, offset)),
             "text_04": maprecords.reference(image, names, u32(image, offset + 4)),
             "sprite_08": "%08x" % u32(image, offset + 8),
             "reserved_0c_0f": maprecords.hexed(image, offset + 0x0C, 4),
             "record_10": "%08x" % u32(image, offset + 0x10)})
    for index, (offset, width) in enumerate(found["roster_string"]):
        rows["roster_string"].append(
            {"label": label("roster_string", index), "address": "%08x" % (offset + ROM_BASE),
             "text": text_content(image, offset, width)})
    for index, (offset, width) in enumerate(found["objective"]):
        rows["objective"].append(
            {"label": label("objective", index), "address": "%08x" % (offset + ROM_BASE),
             "text": text_content(image, offset, width)})
    for index, (offset, _width) in enumerate(found["font"]):
        rows["font"].append({"label": label("font", index),
                             "address": "%08x" % (offset + ROM_BASE),
                             "offset": "%04x" % u16(image, offset)})
    return rows


def uncited_fields(text):
    return maprecords.uncited_fields(text, SPECS)


def read_rom():
    return maprecords.read_rom(ROM, ROM_SHA256)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--null"]:
        image = read_rom()
        result = null(image)
        print("permuted " + " ".join("%s=%d" % (family, result[family]) for family in PINNED))
        differ = differing(image)
        print("differing records "
              + " ".join("%s=%d" % (family, differ[family]) for family in PINNED))
        return 0 if not any(result.values()) and all(differ.values()) else 1
    return maprecords.generator_main(sys.modules[__name__], "text_rows", argv)


if __name__ == "__main__":
    raise SystemExit(main())
