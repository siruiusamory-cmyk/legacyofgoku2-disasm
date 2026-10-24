from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "research"))
sys.path.insert(0, os.path.join(ROOT, "tools", "maprecords"))

import asset_directory
import maprecords

ROM = os.path.join(ROOT, "baserom.gba")
BUILD = os.path.join(ROOT, "build", "sprites")
ROM_BASE = asset_directory.ROM_BASE
ROM_SHA256 = asset_directory.ROM_SHA256
CENSUS_BYTES = 26508
COUNT_LIMIT = 64
REFERENCE = maprecords.REFERENCE

SPECS = {
    "directory": [("reserved_00_0b", 0x00, 0x0C, "bytes"),
                  ("entries", 0x0C, 4, "refs")],
    "definition": [("reserved_00_03", 0x00, 4, "bytes"), ("count", 0x04, 4, "u32"),
                   ("reserved_08_4b", 0x08, 0x44, "bytes"), ("slots", 0x4C, 4, "refs")],
    "piece": [("x", 0x00, 1, "int8"), ("y", 0x01, 1, "int8"),
              ("w", 0x02, 1, "uint8"), ("h", 0x03, 1, "uint8"), ("attribute", 0x04, 4, "u32"),
              ("graphics", 0x08, 4, "u32")],
}
PINNED = {"directory": 1, "definition": 150, "piece": 776}


def u32(image, offset):
    return int.from_bytes(image[offset:offset + 4], "little")


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def label(family, index):
    return "%s_%03d" % ({"definition": "def", "piece": "piece"}.get(family, family), index)


def walk(image):
    addresses = asset_directory.table(image)
    definitions, pieces, named, piece_names = [], [], {}, {}
    for address in addresses:
        offset = address - ROM_BASE
        count = u32(image, offset + asset_directory.COUNT_FIELD)
        if not 0 < count <= COUNT_LIMIT or offset in named:
            continue
        named[offset] = label("definition", len(definitions))
        definitions.append((offset, asset_directory.SLOT_FIELD + 4 * count))
        for index in range(count):
            pointer = u32(image, offset + asset_directory.SLOT_FIELD + 4 * index)
            if not in_image(image, pointer) or pointer in piece_names:
                continue
            try:
                asset_directory.pieces(image, pointer)
            except ValueError:
                continue
            piece_names[pointer] = label("piece", len(piece_names))
            pieces.append((pointer - ROM_BASE, asset_directory.PIECE))
    return {"directory": [(asset_directory.TABLE, 0x0C + 4 * len(addresses))],
            "definition": definitions, "piece": pieces,
            "names": named, "piece_names": piece_names, "entries": addresses}


def extents(found):
    return {"directory": found["directory"], "definition": found["definition"],
            "piece": found["piece"]}


def names_of(found):
    names = dict(found["names"])
    names.update({address - ROM_BASE: name
                  for address, name in found["piece_names"].items()})
    return names


def labels_of(rows):
    return {row["label"]: int(row["address"], 16) - ROM_BASE
            for family in rows.values() for row in family}


def encode_row(family, row, labels):
    return maprecords.encode_row(family, row, labels, SPECS)


def load_tables(directory=None):
    return maprecords.load_tables(PINNED, SPECS, directory or HERE)


def write_tables(tables, directory=None):
    maprecords.write_tables(tables, SPECS, directory or HERE)


def build_records(rows, found, holes=None):
    return maprecords.build_records(rows, holes, found, SPECS, PINNED)


def runs(records):
    return maprecords.runs(records)


def tokens(image, rows=None):
    return [(begin, end, "build\\sprites\\rec_%x_%x.bin" % (begin, end))
            for begin, end in runs(build_records(rows or load_tables(), walk(image)))]


def write(image, rows=None):
    return maprecords.write_runs(build_records(rows or load_tables(), walk(image)), BUILD, "rec")


def check(image, rows=None):
    records = build_records(rows or load_tables(), walk(image))
    mismatched = sum(1 for offset, data, _spans in records
                     if image[offset:offset + len(data)] != data)
    return {"records": len(records), "mismatched_records": mismatched,
            "bytes": sum(len(data) for _offset, data, _spans in records),
            "emitted_bytes": sum(stop - begin for _offset, _data, spans in records
                                 for begin, stop in spans)}


def counts(image):
    result = {family: 0 for family in PINNED}
    try:
        addresses = asset_directory.table(image)
    except ValueError:
        addresses = []
    result["directory"] = 1 if addresses else 0
    pieces = set()
    for address in addresses:
        offset = address - ROM_BASE
        count = u32(image, offset + asset_directory.COUNT_FIELD)
        if not 0 < count <= COUNT_LIMIT:
            continue
        result["definition"] += 1
        for index in range(count):
            pointer = u32(image, offset + asset_directory.SLOT_FIELD + 4 * index)
            if not in_image(image, pointer) or pointer in pieces:
                continue
            try:
                asset_directory.pieces(image, pointer)
            except ValueError:
                continue
            pieces.add(pointer)
    result["piece"] = len(pieces)
    return result


def permuted(image, spans):
    out = bytearray(image)
    for begin, end in spans:
        pairs = [out[at:at + 2] for at in range(begin, end - 1, 2)]
        pairs.reverse()
        out[begin:begin + 2 * len(pairs)] = b"".join(pairs)
    return bytes(out)


def null(image, families=None):
    found = walk(image)
    places = extents(found)
    chosen = families or tuple(PINNED)
    spans = [(offset, offset + width) for family in chosen for offset, width in places[family]]
    return counts(permuted(image, spans))


def reference(image, names, address):
    if not in_image(image, address):
        return "%08x" % address
    return names.get(address - ROM_BASE, "%08x" % address)


def hexed(image, offset, width):
    return image[offset:offset + width].hex()


def extract(image):
    found = walk(image)
    names = names_of(found)
    rows = {family: [] for family in PINNED}
    offset = asset_directory.TABLE
    rows["directory"].append(
        {"label": "directory", "address": "%08x" % (offset + ROM_BASE),
         "reserved_00_0b": hexed(image, offset, 0x0C),
         "entries": " ".join(reference(image, names, address) for address in found["entries"])})
    for index, (offset, width) in enumerate(found["definition"]):
        count = u32(image, offset + asset_directory.COUNT_FIELD)
        rows["definition"].append(
            {"label": label("definition", index), "address": "%08x" % (offset + ROM_BASE),
             "reserved_00_03": hexed(image, offset, 4), "count": "%08x" % count,
             "reserved_08_4b": hexed(image, offset + 8, 0x44),
             "slots": " ".join(reference(image, names,
                                        u32(image, offset + asset_directory.SLOT_FIELD + 4 * slot))
                               for slot in range(count))})
    for index, (offset, _width) in enumerate(found["piece"]):
        x, y, w, h = (int.from_bytes(image[offset:offset + 1], "little", signed=True),
                      int.from_bytes(image[offset + 1:offset + 2], "little", signed=True),
                      image[offset + 2], image[offset + 3])
        rows["piece"].append(
            {"label": label("piece", index), "address": "%08x" % (offset + ROM_BASE),
             "x": "%d" % x, "y": "%d" % y, "w": "%d" % w, "h": "%d" % h,
             "attribute": "%08x" % u32(image, offset + 4),
             "graphics": "%08x" % u32(image, offset + 8)})
    return rows


def uncited_fields(text):
    return maprecords.uncited_fields(text, SPECS)


def read_rom():
    return maprecords.read_rom(ROM, ROM_SHA256)


def main(argv=None):
    return maprecords.generator_main(sys.modules[__name__], "sprites", argv)


if __name__ == "__main__":
    raise SystemExit(main())
