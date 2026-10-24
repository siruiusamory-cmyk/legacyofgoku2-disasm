from __future__ import annotations

import csv
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "gate"))
sys.path.insert(0, os.path.join(ROOT, "tools", "compress"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mapcontainer"))
sys.path.insert(0, os.path.join(ROOT, "tools", "text"))
sys.path.insert(0, HERE)

import asset_directory
import gate
import mapcontainer
import opcode_stream
import text_storage

ROM = os.path.join(ROOT, "baserom.gba")
DOC = os.path.join(ROOT, "tools", "research", "DATA_CENSUS.md")
CONTAINERS = os.path.join(ROOT, "tools", "compress", "CONTAINER_CENSUS.csv")
CODE_SPLIT = os.path.join(ROOT, "tools", "split", "CODE_SPLIT.csv")
ROM_BASE = 0x08000000
IMAGE_BYTES = 8388608
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
REGION_BYTES = 3630726
REGION_EXTENTS = 6449
FILL = 8
ADDRESS_RUN = 2
UNREAD = "no reader found"
FILL_CLASS = UNREAD + ": fill run"
ADDRESS_CLASS = UNREAD + ": address run"
RESIDUAL_CLASS = UNREAD + ": residual"
MAP_ENTRY = 0x08409368
MAP_ENTRY_STRIDE = 0x38
SPRITE_TABLE = asset_directory.TABLE
SPRITE_ENTRIES = 154
SPRITE_NULL = 3
SPRITE_DEFINITION = 0x08009324
SPRITE_SLOTS = 0x4C
SPRITE_PIECE = 12
OPCODE_QUEST = 0x086D68DC
OPCODE_STRIDE = 16
OPCODE_RECORD = 0x080092E4
OPCODE_STREAM = 0x080092E4
TEXT_DRAW = 0x0801F702
FONT_TABLE = 0x0028724
FONT_CODES = 256
MAP_ROOT_READER = 0x0800EB4C
MAP_LAYER_READER = 0x08005300


def u32(image, offset):
    return int.from_bytes(image[offset:offset + 4], "little")


def in_image(image, address):
    return ROM_BASE <= address < ROM_BASE + len(image)


def contains(extents, site):
    return any(begin <= site < end for begin, end in extents)


def read_rom(path=None):
    path = path or ROM
    if not os.path.exists(path):
        raise SystemExit("the data census needs the retail image at %s" % path)
    image = open(path, "rb").read()
    if hashlib.sha256(image).hexdigest() != ROM_SHA256:
        raise SystemExit("%s is not the canonical image" % path)
    return image


def region_mask(image):
    mask = bytearray(len(image))
    for start, length in gate.incbin_ranges(ROOT):
        mask[start:start + length] = b"\x01" * length
    for row in csv.DictReader(open(CONTAINERS, encoding="ascii")):
        offset = int(row["offset"], 16)
        mask[offset:offset + int(row["packed"])] = b"\x00" * int(row["packed"])
    return mask


def region_extents(mask):
    out = []
    begin = None
    for index, value in enumerate(mask):
        if value and begin is None:
            begin = index
        elif not value and begin is not None:
            out.append((begin, index))
            begin = None
    if begin is not None:
        out.append((begin, len(mask)))
    return out


def code_extents(image):
    out = []
    for row in csv.DictReader(open(CODE_SPLIT, encoding="ascii")):
        if "code" not in row["class"]:
            continue
        out.append((int(row["start"], 16) - ROM_BASE, int(row["end"], 16) - ROM_BASE))
    return out


def literal_loads(image):
    sites = {}
    for begin, end in code_extents(image):
        at = begin
        while at + 2 <= end:
            half = image[at] | image[at + 1] << 8
            if half & 0xF800 == 0x4800:
                literal = ((at + 4) & ~3) + (half & 0xFF) * 4
                if literal + 4 <= len(image):
                    value = u32(image, literal)
                    if in_image(image, value):
                        sites.setdefault(value, []).append(at + ROM_BASE)
            at += 2
    return sites


def anchor(sites, value, fallback):
    found = sites.get(value)
    return min(found) if found else fallback


def map_root_arrays(image):
    out = []
    for (base, _limit), slots in zip(mapcontainer.root_arrays(image),
                                    mapcontainer.root_slots(image)):
        if slots:
            out.append((base, base + 4 * len(slots)))
    return out


def sprite_definitions(image):
    definitions, pieces = [], []
    for address in asset_directory.table(image):
        site = address - ROM_BASE
        count = u32(image, site + asset_directory.COUNT_FIELD)
        if not 0 < count <= 64:
            continue
        definitions.append((site, site + SPRITE_SLOTS + 4 * count))
        for index in range(count):
            pointer = u32(image, site + asset_directory.SLOT_FIELD + 4 * index)
            if in_image(image, pointer):
                pieces.append((pointer - ROM_BASE, pointer - ROM_BASE + SPRITE_PIECE))
    return definitions, pieces


def entry_extent(image):
    mapcontainer.map_roots(image)
    return [(site, site + MAP_ENTRY_STRIDE) for site in mapcontainer.entries(image)]


def directory_extent(image):
    entries = asset_directory.table(image)
    return [(SPRITE_TABLE, SPRITE_TABLE + 4 * (SPRITE_NULL + len(entries)))]


def font_extent(image):
    text_storage.font(image)
    return [(FONT_TABLE, FONT_TABLE + 2 * FONT_CODES)]


def family_rows(image, sites, safe=False):
    built = {}

    def sprites():
        if not built:
            built["definition"], built["piece"] = sprite_definitions(image)
        return built

    rows = [
        ("map entry", lambda: entry_extent(image),
         anchor(sites, MAP_ENTRY, MAP_ROOT_READER), "row, stride 0x38, +0x2C names roots"),
        ("map root record",
         lambda: [(site, site + size)
                  for site, size in mapcontainer.record_extents(image)["root_record"]],
         MAP_ROOT_READER, "record, 0x50 B, +0x4C names the tile-bank table"),
        ("map root pointer array", lambda: map_root_arrays(image), MAP_ROOT_READER,
         "word array, one or more root addresses"),
        ("map layer record",
         lambda: [(site, site + size)
                  for site, size in mapcontainer.record_extents(image)["dominant_layer_record"]],
         MAP_LAYER_READER, "record, factory 0x080056A1, +0x18 names chunks"),
        ("map root-table row",
         lambda: [(site, site + size)
                  for site, size in mapcontainer.record_extents(image)["root_table_record"]],
         MAP_ROOT_READER, "row, 24 B, count at root+0x24, base at root+0x28"),
        ("sprite directory", lambda: directory_extent(image),
         anchor(sites, asset_directory.LITERAL_VALUE, SPRITE_DEFINITION),
         "154-entry pointer table after 3 null words"),
        ("sprite definition", lambda: sprites()["definition"], SPRITE_DEFINITION,
         "record, count at +0x04, slot array at +0x4C"),
        ("sprite piece", lambda: sprites()["piece"], SPRITE_DEFINITION, "12-byte piece, +8 names a container"),
        ("opcode record", lambda: [(record_at, record_at + OPCODE_STRIDE)
                                   for record_at, _addresses in opcode_stream.streams(image)],
         anchor(sites, OPCODE_QUEST, OPCODE_RECORD),
         "row, stride 16, +0x04/+0x08 name streams, +0x0C names text"),
        ("opcode stream", lambda: [(row["start"], row["stop"])
                                   for row in opcode_stream.census(image)
                                   if row["problem"] is None],
         OPCODE_STREAM, "byte stream, ends on 0x11"),
        ("text string", lambda: [(row["address"] - ROM_BASE,
                                  row["address"] - ROM_BASE + row["length"] + 1)
                                 for row in text_storage.objectives(image)],
         TEXT_DRAW, "byte codes, NUL-terminated"),
        ("font table", lambda: font_extent(image),
         anchor(sites, FONT_TABLE + ROM_BASE, TEXT_DRAW), "256-entry u16 record widths"),
    ]
    out = []
    for name, thunk, reader, text in rows:
        try:
            extents = thunk()
        except ValueError:
            if not safe:
                raise
            extents = []
        out.append({"name": name, "extents": extents, "reader": reader, "format": text})
    return out


def fill_runs(image, mask):
    out = []
    for begin, end in region_extents(mask):
        index = begin
        while index < end:
            value = image[index]
            run = index
            while run < end and image[run] == value:
                run += 1
            if value in (0x00, 0xFF) and run - index >= FILL:
                out.append((index, run))
            index = run
    return out


def address_runs(image, mask):
    out = []
    for begin, end in region_extents(mask):
        index = (begin + 3) & ~3
        first = last = None
        while index + 4 <= end:
            word = u32(image, index)
            if in_image(image, word):
                first = index if first is None else first
                last = index
            else:
                if first is not None and last - first >= 4 * (ADDRESS_RUN - 1):
                    out.append((first, last + 4))
                first = last = None
            index += 4
        if first is not None and last - first >= 4 * (ADDRESS_RUN - 1):
            out.append((first, last + 4))
    return out


def claim(marks, mask, number, extents):
    for begin, end in extents:
        if not 0 <= begin < end <= len(marks):
            raise ValueError("extent %d..%d is not a start and an end inside the image"
                             % (begin, end))
        for index in range(begin, end):
            if mask[index] and not marks[index]:
                marks[index] = number


def count(marks, mask):
    rows, order = {}, []
    for begin, end in region_extents(mask):
        index = begin
        while index < end:
            value = marks[index]
            run = index
            while run < end and marks[run] == value:
                run += 1
            if value not in rows:
                rows[value] = {"bytes": 0, "extents": 0}
                order.append(value)
            rows[value]["bytes"] += run - index
            rows[value]["extents"] += 1
            index = run
    return rows, order


def classify(image, mask, safe=False):
    sites = literal_loads(image)
    families = family_rows(image, sites, safe)
    marks = bytearray(len(image))
    for number, family in enumerate(families, start=1):
        claim(marks, mask, number, family["extents"])
    fill_number = len(families) + 1
    claim(marks, mask, fill_number, fill_runs(image, mask))
    address_number = len(families) + 2
    claim(marks, mask, address_number, address_runs(image, mask))
    rows, order = count(marks, mask)
    names = {0: RESIDUAL_CLASS, fill_number: FILL_CLASS, address_number: ADDRESS_CLASS}
    table = []
    for number in order:
        if number in names:
            name, reader, text = names[number], None, "no reader: the bytes the three searches left"
        else:
            family = families[number - 1]
            name, reader, text = family["name"], family["reader"], family["format"]
        table.append({"name": name, "bytes": rows[number]["bytes"],
                      "extents": rows[number]["extents"], "reader": reader, "format": text})
    table.sort(key=lambda row: (-row["bytes"], row["name"]))
    total = sum(row["bytes"] for row in table)
    reader_bytes = sum(row["bytes"] for row in table if row["reader"])
    named = sorted({value - ROM_BASE for value in sites
                    if 0 <= value - ROM_BASE < len(mask) and mask[value - ROM_BASE]})
    owned = [value for value in named
             if any(contains(family["extents"], value) for family in families)]
    biggest = sorted(((end - begin, begin, end) for begin, end in region_extents(mask)),
                     reverse=True)[:8]
    return {"rows": table, "total": total, "reader_bytes": reader_bytes,
            "region_extents": len(region_extents(mask)),
            "class_extents": sum(row["extents"] for row in table),
            "sites": sum(len(hits) for hits in sites.values()),
            "bases": len(named), "bases_owned": len(owned),
            "biggest": [(begin, end, len([value for value in named if begin <= value < end]))
                        for _size, begin, end in biggest]}


def census(image):
    return classify(image, region_mask(image))


def permuted(image, mask):
    out = bytearray(image)
    for begin, end in region_extents(mask):
        pairs = [out[at:at + 2] for at in range(begin, end - 1, 2)]
        pairs.reverse()
        out[begin:begin + 2 * len(pairs)] = b"".join(pairs)
    return bytes(out)


def null_census(image):
    mask = region_mask(image)
    return classify(permuted(image, mask), mask, True)


def doc_text(result, null):
    lines = []
    add = lines.append
    add("# The data outside every container")
    add("")
    add("Generated by `python tools\\research\\data_census.py --write`; `--check` re-derives this "
        "page from the builder's image and refuses a difference.")
    add("")
    add("## Method")
    add("")
    add("The measured region is the gate's own class: every byte the asm files INCBIN from the "
        "image (`gate.incbin_ranges`), less the extents of the accepted containers in "
        "`CONTAINER_CENSUS.csv`. It is %d B in %d extents, and the container census owns the rest "
        "of the gate's raw class. Those extents hold %d class runs, and a class extent is one "
        "maximal run of that class inside them."
        % (result["total"], result["region_extents"], result["class_extents"]))
    add("")
    add("A byte is classed by the first of these rules that claims it. A **reader class** is a "
        "record family whose extents this tree already decodes, and its reader is a load site in "
        "the split's walked code (a `CODE_SPLIT.csv` code extent) that names the family's base in "
        "its literal pool; where the base is reached through a pointer and no literal names it, "
        "the reader is the decoder's own code site. A **%s** class is a run of at least %d fill "
        "bytes, a **%s** class is two or more consecutive 4-aligned words that name the image, "
        "and the **%s** is what those rules leave." % (FILL_CLASS, FILL, ADDRESS_CLASS,
                                                       RESIDUAL_CLASS))
    add("")
    add("The three non-reader classes are labelled `%s`: the game's code has no decoder here. "
        "They are shapes, not formats, and a shape is not a reader." % UNREAD)
    add("")
    add("The null keeps the region's extents and permutes their bytes, reversing the halfword "
        "order inside every extent, so the same decoders run over the same address set with no "
        "byte structure left. A reader class that survives that run is not reading structure.")
    add("")
    add("## Classes")
    add("")
    add("| class | bytes | extents | reader load site | format | bytes a generator would move |")
    add("|---|---|---|---|---|---|")
    for row in result["rows"]:
        add("| %s | %d | %d | %s | %s | %d |"
            % (row["name"], row["bytes"], row["extents"],
               "`0x%08X`" % row["reader"] if row["reader"] else "-", row["format"],
               row["bytes"] if row["reader"] else 0))
    add("| total | %d | %d | | | %d |"
        % (result["total"], result["class_extents"], result["reader_bytes"]))
    add("")
    add("A reader class moves its own bytes because the tree already decodes the family and "
        "re-emits it from that decode; a class with no reader moves none until a format is named.")
    add("")
    add("## Null")
    add("")
    add("| measure | image | permuted bytes |")
    add("|---|---|---|")
    add("| reader-backed bytes | %d | %d |" % (result["reader_bytes"], null["reader_bytes"]))
    add("| classes with a reader | %d | %d |"
        % (len([row for row in result["rows"] if row["reader"]]),
           len([row for row in null["rows"] if row["reader"]])))
    add("| total | %d | %d |" % (result["total"], null["total"]))
    add("")
    add("## Reader bases")
    add("")
    add("The split's walked code holds %d Thumb `ldr` literals that name an image address, and "
        "%d of those bases lie in the region. %d of them fall inside a reader class, so %d are "
        "bases the game's code names and no decoder in this tree reads: they are the generator "
        "leads a class table cannot price." % (result["sites"], result["bases"],
                                               result["bases_owned"],
                                               result["bases"] - result["bases_owned"]))
    add("")
    add("## The largest region extents")
    add("")
    add("| extent | bytes | bases the code names inside it |")
    add("|---|---|---|")
    for begin, end, hits in result["biggest"]:
        add("| `0x%06X..0x%06X` | %d | %d |" % (begin, end, end - begin, hits))
    add("")
    add("## Reproduce")
    add("")
    add("    python tools\\research\\data_census.py --check")
    add("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--write"], ["--check"], ["--null"]):
        print("usage: python tools\\research\\data_census.py [--write|--check|--null]")
        return 2
    image = read_rom()
    result = census(image)
    null = null_census(image)
    print("region=%d B extents=%d" % (result["total"], result["region_extents"]))
    for row in result["rows"]:
        print("%-28s %8d B %5d extents %s"
              % (row["name"], row["bytes"], row["extents"],
                 "reader 0x%08X" % row["reader"] if row["reader"] else UNREAD))
    print("reader-backed=%d B null=%d B bases named by code=%d of %d literal loads"
          % (result["reader_bytes"], null["reader_bytes"], result["bases"], result["sites"]))
    if result["total"] != REGION_BYTES or result["region_extents"] != REGION_EXTENTS:
        print("DATA FAIL: the region is %d B in %d extents, not %d B in %d"
              % (result["total"], result["region_extents"], REGION_BYTES, REGION_EXTENTS))
        return 1
    if null["reader_bytes"]:
        print("DATA FAIL: the permuted region still carries %d reader-backed bytes"
              % null["reader_bytes"])
        return 1
    if argv == ["--null"]:
        return 0
    text = doc_text(result, null)
    if argv == ["--write"]:
        with open(DOC, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("wrote %s" % os.path.basename(DOC))
        return 0
    if argv == ["--check"]:
        current = open(DOC, encoding="utf-8", newline="").read() if os.path.exists(DOC) else None
        if current != text:
            print("DATA FAIL: %s is not what this image derives" % os.path.basename(DOC))
            return 1
        print("DATA PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
