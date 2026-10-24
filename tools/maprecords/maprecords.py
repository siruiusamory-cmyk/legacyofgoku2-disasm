from __future__ import annotations

import bisect
import csv
import hashlib
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "mapcontainer"))

import mapcontainer

ROM = os.path.join(ROOT, "baserom.gba")
CONTAINERS = os.path.join(ROOT, "tools", "compress", "CONTAINER_CENSUS.csv")
BUILD = os.path.join(ROOT, "build", "maprecords")
ROM_BASE = 0x08000000
ROM_SHA256 = mapcontainer.ROM_SHA256
CENSUS_BYTES = 46397
WINDOW = 0x20000
PINNED = {"entry": 327, "root": 336, "array": 327, "layer": 1294, "row": 710}
REFERENCE = re.compile(r"^[a-z]+_[0-9]{3,4}$")
HEX = re.compile(r"^[0-9a-f]+$")

SPECS = {
    "entry": [("field_00", 0x00, 1, "u8"), ("field_01", 0x01, 1, "u8"),
              ("field_02", 0x02, 1, "u8"), ("reserved_03_2b", 0x03, 0x29, "bytes"),
              ("root_array", 0x2C, 4, "ref"), ("reserved_30_37", 0x30, 8, "bytes")],
    "root": [("reserved_00_13", 0x00, 0x14, "bytes"),
             ("layer_0", 0x14, 4, "ref"), ("layer_1", 0x18, 4, "ref"),
             ("layer_2", 0x1C, 4, "ref"), ("layer_3", 0x20, 4, "ref"),
             ("row_count", 0x24, 4, "u32"), ("row_table", 0x28, 4, "ref"),
             ("reserved_2c_47", 0x2C, 0x1C, "bytes"), ("container_48", 0x48, 4, "ref"),
             ("tile_banks", 0x4C, 4, "ref")],
    "array": [("roots", 0x00, 4, "refs")],
    "layer": [("handler", 0x00, 4, "ref"), ("declared", 0x04, 4, "u32"),
              ("reserved_08_13", 0x08, 0x0C, "bytes"), ("rows", 0x14, 1, "u8"),
              ("columns", 0x15, 1, "u8"), ("reserved_16_17", 0x16, 2, "bytes"),
              ("chunks", 0x18, 4, "refs")],
    "row": [("word_00", 0x00, 4, "u32"), ("word_04", 0x04, 4, "u32"),
            ("word_08", 0x08, 4, "u32"), ("word_0c", 0x0C, 4, "u32"),
            ("reserved_10_15", 0x10, 6, "bytes"), ("byte_16", 0x16, 1, "u8"),
            ("byte_17", 0x17, 1, "u8")],
}


def u32(image, offset):
    return struct.unpack_from("<I", image, offset)[0]


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def label(family, index):
    return "%s_%0*d" % (family, 4 if family == "layer" else 3, index)


def walk(image):
    entries = mapcontainer.entries(image)
    bases = [u32(image, offset + mapcontainer.ENTRY_ROOT) - ROM_BASE for offset in entries]
    arrays, roots = [], []
    for index, base in enumerate(bases):
        later = [other for other in bases[index + 1:] if other > base]
        limit = min(later) if later else base + mapcontainer.ROOT_EXTENT
        slots = []
        while base + 4 <= limit and mapcontainer.root_slot(image, u32(image, base)):
            slots.append(u32(image, base) - ROM_BASE)
            base += 4
        arrays.append((bases[index], bases[index] + 4 * len(slots)))
        roots += slots
    roots = sorted(set(roots))
    layers = sorted({u32(image, root + mapcontainer.SLOT_BASE + 4 * slot) - ROM_BASE
                     for root in roots for slot in range(mapcontainer.SLOT_COUNT)
                     if in_image(image, u32(image, root + mapcontainer.SLOT_BASE + 4 * slot))
                     and u32(image, u32(image, root + mapcontainer.SLOT_BASE + 4 * slot) - ROM_BASE)
                     == mapcontainer.FACTORY})
    rows = []
    for root in roots:
        count, base = u32(image, root + mapcontainer.ROOT_TABLE_COUNT), \
            u32(image, root + mapcontainer.ROOT_TABLE_BASE)
        if not count or not in_image(image, base):
            continue
        rows.append((count, base - ROM_BASE))
    return {"entry": entries, "root": roots, "array": arrays, "layer": layers, "row": rows}


def extents(image, found=None):
    found = found or walk(image)
    out = {"entry": [], "root": [], "array": [], "layer": [], "row": []}
    out["entry"] = [(offset, 0x38) for offset in found["entry"]]
    out["root"] = [(offset, 0x50) for offset in found["root"]]
    out["array"] = [(start, end - start) for start, end in found["array"]]
    out["layer"] = [(site, mapcontainer.CHUNK_FIELD + 4 * mapcontainer.chunk_count(image, site))
                    for site in found["layer"]]
    out["row"] = [(base + mapcontainer.ROOT_TABLE_STRIDE * index,
                   mapcontainer.ROOT_TABLE_STRIDE) for count, base in found["row"]
                  for index in range(count)]
    return out


def names_of(image, found=None):
    found = found or walk(image)
    places = extents(image, found)
    names = {}
    for family in ("entry", "root", "array", "layer", "row"):
        for index, (offset, _width) in enumerate(places[family]):
            names[offset] = label(family, index)
    return names


def labels_of(rows):
    return {row["label"]: int(row["address"], 16) - ROM_BASE
            for family in rows.values() for row in family}


def array_words(row):
    return row["roots"].split() if row["roots"] else []


def value_of(text, labels):
    if REFERENCE.match(text):
        if text not in labels:
            raise ValueError("%s is not a record of this table" % text)
        return labels[text] + ROM_BASE
    if not HEX.match(text) or len(text) % 2:
        raise ValueError("%r is neither a record label nor hex" % text)
    return int(text, 16)


def encode_row(family, row, labels, specs=None):
    out = bytearray()
    for name, offset, width, kind in (SPECS if specs is None else specs)[family]:
        if len(out) != offset:
            raise ValueError("%s.%s starts at 0x%X, not 0x%X" % (family, name, offset, len(out)))
        if kind == "bytes":
            data = bytes.fromhex(row[name])
            if len(data) != width:
                raise ValueError("%s.%s holds %d B, not %d" % (family, name, len(data), width))
            out += data
        elif kind == "ref":
            out += value_of(row[name], labels).to_bytes(4, "little")
        elif kind == "refs":
            words = row[name].split()
            if not words:
                raise ValueError("%s.%s holds no reference" % (family, name))
            for word in words:
                out += value_of(word, labels).to_bytes(4, "little")
        elif kind == "string":
            out += row[name].encode("ascii") + b"\x00"
        elif kind in ("int8", "uint8"):
            out += int(row[name]).to_bytes(width, "little", signed=kind == "int8")
        else:
            out += int(row[name], 16).to_bytes(width, "little")
    return bytes(out)


def load_tables(pinned=None, specs=None, directory=None):
    directory = directory or HERE
    tables = {}
    for family, count in (PINNED if pinned is None else pinned).items():
        path = os.path.join(directory, family + ".csv")
        rows = list(csv.DictReader(open(path, encoding="utf-8", newline="")))
        if len(rows) != count:
            raise ValueError("%s holds %d rows, not %d" % (path, len(rows), count))
        tables[family] = rows
    return tables


def write_tables(tables, specs=None, directory=None):
    directory = directory or HERE
    specs = SPECS if specs is None else specs
    for family, rows in tables.items():
        names = ["label", "address"] + [field[0] for field in specs[family]]
        path = os.path.join(directory, family + ".csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore",
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def container_extents():
    return sorted((int(row["offset"], 16), int(row["offset"], 16) + int(row["packed"]))
                  for row in csv.DictReader(open(CONTAINERS, encoding="ascii")))


def uncovered(offset, width, holes, starts=None):
    starts = starts if starts is not None else [begin for begin, _end in holes]
    spans = [(offset, offset + width)]
    for begin, end in holes[bisect.bisect_left(starts, offset - WINDOW):]:
        if begin >= offset + width:
            break
        nxt = []
        for start, stop in spans:
            if end <= start or begin >= stop:
                nxt.append((start, stop))
                continue
            if start < begin:
                nxt.append((start, begin))
            if end < stop:
                nxt.append((end, stop))
        spans = nxt
    return spans


def build_records(rows, holes=None, found=None, specs=None, pinned=None):
    holes = container_extents() if holes is None else holes
    specs = SPECS if specs is None else specs
    labels = labels_of(rows)
    records = []
    for family in (PINNED if pinned is None else pinned):
        places = None if found is None else found[family]
        if places is not None and len(places) != len(rows[family]):
            raise ValueError("%s holds %d row(s) for %d record(s)"
                             % (family, len(rows[family]), len(places)))
        for index, row in enumerate(rows[family]):
            offset = int(row["address"], 16) - ROM_BASE
            if places is not None and places[index][0] != offset:
                raise ValueError("%s.%s names 0x%X, not 0x%X"
                                 % (family, row["label"], offset, places[index][0]))
            data = encode_row(family, row, labels, specs)
            if places is not None and len(data) != places[index][1]:
                raise ValueError("%s.%s encodes %d B, not %d"
                                 % (family, row["label"], len(data), places[index][1]))
            records.append((offset, data, uncovered(offset, len(data), holes)))
    records.sort()
    return records


def runs(records):
    found = sorted(span for _offset, _data, spans in records for span in spans)
    merged = []
    for begin, end in found:
        if merged and merged[-1][1] == begin:
            merged[-1][1] = end
        else:
            merged.append([begin, end])
    return [(begin, end) for begin, end in merged]


def tokens(image, rows=None):
    return [(begin, end, "build\\maprecords\\rec_%x_%x.bin" % (begin, end))
            for begin, end in runs(build_records(rows or load_tables()))]


def write_runs(records, directory, prefix):
    os.makedirs(directory, exist_ok=True)
    written = 0
    for start, end in runs(records):
        blob = bytearray()
        for offset, data, spans in records:
            if offset >= end or offset + len(data) <= start:
                continue
            for begin, stop in spans:
                if start <= begin and stop <= end:
                    blob += data[begin - offset:stop - offset]
        if len(blob) != end - start:
            raise ValueError("the run 0x%X..0x%X assembled %d B" % (start, end, len(blob)))
        with open(os.path.join(directory, "%s_%x_%x.bin" % (prefix, start, end)), "wb") as handle:
            handle.write(bytes(blob))
        written += 1
    return written, len(records)


def write(image, rows=None):
    return write_runs(build_records(rows or load_tables()), BUILD, "rec")


def check(image, rows=None):
    records = build_records(rows or load_tables())
    mismatched = sum(1 for offset, data, _spans in records
                     if image[offset:offset + len(data)] != data)
    return {"records": len(records), "mismatched_records": mismatched,
            "bytes": sum(len(data) for _offset, data, _spans in records),
            "emitted_bytes": sum(stop - begin for _offset, _data, spans in records
                                 for begin, stop in spans)}


def reference(image, names, address):
    if not in_image(image, address):
        return "%08x" % address
    return names.get(address - ROM_BASE, "%08x" % address)


def hexed(image, offset, width):
    return image[offset:offset + width].hex()


def entry_row(image, names, index, offset):
    return {"label": label("entry", index), "address": "%08x" % (offset + ROM_BASE),
            "field_00": "%02x" % image[offset], "field_01": "%02x" % image[offset + 1],
            "field_02": "%02x" % image[offset + 2],
            "reserved_03_2b": hexed(image, offset + 3, 0x29),
            "root_array": reference(image, names, u32(image, offset + 0x2C)),
            "reserved_30_37": hexed(image, offset + 0x30, 8)}


def root_row(image, names, index, offset):
    row = {"label": label("root", index), "address": "%08x" % (offset + ROM_BASE),
           "reserved_00_13": hexed(image, offset, 0x14),
           "row_count": "%08x" % u32(image, offset + 0x24),
           "row_table": reference(image, names, u32(image, offset + 0x28)),
           "reserved_2c_47": hexed(image, offset + 0x2C, 0x1C),
           "container_48": reference(image, names, u32(image, offset + 0x48)),
           "tile_banks": "%08x" % u32(image, offset + 0x4C)}
    for slot in range(4):
        row["layer_%d" % slot] = reference(image, names, u32(image, offset + 0x14 + 4 * slot))
    return row


def layer_row(image, names, index, offset):
    count = mapcontainer.chunk_count(image, offset)
    return {"label": label("layer", index), "address": "%08x" % (offset + ROM_BASE),
            "handler": reference(image, names, u32(image, offset)),
            "declared": "%08x" % u32(image, offset + 4),
            "reserved_08_13": hexed(image, offset + 8, 0x0C),
            "rows": "%02x" % image[offset + 0x14], "columns": "%02x" % image[offset + 0x15],
            "reserved_16_17": hexed(image, offset + 0x16, 2),
            "chunks": " ".join("%08x" % u32(image, offset + 0x18 + 4 * i) for i in range(count))}


def row_row(image, index, offset):
    return {"label": label("row", index), "address": "%08x" % (offset + ROM_BASE),
            "word_00": "%08x" % u32(image, offset), "word_04": "%08x" % u32(image, offset + 4),
            "word_08": "%08x" % u32(image, offset + 8), "word_0c": "%08x" % u32(image, offset + 0xC),
            "reserved_10_15": hexed(image, offset + 0x10, 6),
            "byte_16": "%02x" % image[offset + 0x16], "byte_17": "%02x" % image[offset + 0x17]}


def extract(image):
    found = walk(image)
    places = extents(image, found)
    names = names_of(image, found)
    rows = {family: [] for family in PINNED}
    for index, (offset, _width) in enumerate(places["entry"]):
        rows["entry"].append(entry_row(image, names, index, offset))
    for index, (offset, _width) in enumerate(places["root"]):
        rows["root"].append(root_row(image, names, index, offset))
    for index, (offset, _width) in enumerate(places["array"]):
        end = min(offset + _width, len(image))
        rows["array"].append({"label": label("array", index),
                              "address": "%08x" % (offset + ROM_BASE),
                              "roots": " ".join(reference(image, names, u32(image, at))
                                                for at in range(offset, end, 4))})
    for index, (offset, _width) in enumerate(places["layer"]):
        rows["layer"].append(layer_row(image, names, index, offset))
    for index, (offset, _width) in enumerate(places["row"]):
        rows["row"].append(row_row(image, index, offset))
    return rows


def permuted(image, spans):
    out = bytearray(image)
    for begin, end in spans:
        pairs = [out[at:at + 2] for at in range(begin, end - 1, 2)]
        pairs.reverse()
        out[begin:begin + 2 * len(pairs)] = b"".join(pairs)
    return bytes(out)


def null(image):
    places = extents(image)
    spans = [(offset, offset + width) for family in ("entry", "root", "array", "layer", "row")
             for offset, width in places[family]]
    try:
        found = walk(permuted(image, spans))
    except ValueError:
        return {family: 0 for family in PINNED}
    counts = extents(image, found)
    return {family: len(counts[family]) for family in PINNED}


def uncited_fields(text, specs=None):
    specs = SPECS if specs is None else specs
    sections, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
        elif current in specs and line.startswith("| "):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 4 and cells[0] != "field":
                sections.setdefault(current, {})[cells[0]] = cells[3]
    problems = []
    for family, fields in specs.items():
        named = {name for name, _offset, _width, kind in fields if kind != "bytes"}
        cited = {name for name, site in sections.get(family, {}).items() if site != "-"}
        problems += ["%s.%s has no load site" % (family, name)
                     for name in sorted(named - cited)]
        problems += ["%s.%s is not a field" % (family, name)
                     for name in sorted(cited - named)]
    return problems


def read_rom(path=None, digest=None):
    path = path or ROM
    digest = digest or ROM_SHA256
    if not os.path.exists(path):
        raise SystemExit("the record generator needs the retail image at %s" % path)
    image = open(path, "rb").read()
    if hashlib.sha256(image).hexdigest() != digest:
        raise SystemExit("%s is not the canonical image" % path)
    return image


def generator_main(module, name, argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--write"], ["--check"], ["--extract"], ["--null"]):
        print("usage: python tools\\%s\\%s.py [--write|--check|--extract|--null]" % (name, name))
        return 2
    image = module.read_rom()
    if argv == ["--null"]:
        counts = module.null(image)
        print("permuted " + " ".join("%s=%d" % (family, counts[family])
                                     for family in module.PINNED))
        return 1 if any(counts.values()) else 0
    if argv == ["--extract"]:
        module.write_tables(module.extract(image))
        print("wrote " + ", ".join(family + ".csv" for family in module.PINNED))
        return 0
    if argv == ["--write"]:
        written, records = module.write(image)
        print("wrote %d run(s) holding %d record(s)" % (written, records))
        return 0
    result = module.check(image)
    print("records=%d mismatched=%d bytes=%d emitted=%d"
          % (result["records"], result["mismatched_records"], result["bytes"],
             result["emitted_bytes"]))
    if result["mismatched_records"]:
        print("%s FAIL: the table does not hold the image bytes" % name.upper())
        return 1
    if result["emitted_bytes"] != module.CENSUS_BYTES:
        print("%s FAIL: the emitted bytes are not the census class %d"
              % (name.upper(), module.CENSUS_BYTES))
        return 1
    print("%s PASS" % name.upper())
    return 0


def main(argv=None):
    return generator_main(sys.modules[__name__], "maprecords", argv)


if __name__ == "__main__":
    raise SystemExit(main())
