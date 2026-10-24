from __future__ import annotations

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "research"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mapcontainer"))
sys.path.insert(0, os.path.join(ROOT, "tools", "tilebank"))
sys.path.insert(0, os.path.join(ROOT, "tools", "text"))

import asset_directory
import mapcontainer
import opcode_stream
import text_storage
import tilebank

ROM = os.path.join(ROOT, "baserom.gba")
DOC = os.path.join(ROOT, "tools", "research", "FORMAT_REUSE.md")
ROM_SHA256 = mapcontainer.ROM_SHA256
CONTAINERS = 13913
CONTAINER_BYTES = 4775808
PACKED = 9919
IMAGE_BYTES = 8388608
WIDE_RUNS = 84
WIDE_BYTES = 1768
CHARACTER_BANK_DECLARED = 4096
MAP_BANK_DECLARED = 16384


def measure(image):
    return {"map": mapcontainer.measure(image), "streams": opcode_stream.totals(
        opcode_stream.census(image)), "asset": asset_directory.measure(image),
        "banks": tilebank.measure(image), "text": text_storage.measure(image)}


def verdict_rows(result):
    map_counts = result["map"][0]
    streams = result["streams"]
    asset = result["asset"]
    banks = result["banks"]
    text = result["text"]
    return [
        ("packed container (JCALG1)", "SAME",
         "%d B = %.1f %% of the image" % (CONTAINER_BYTES, 100.0 * CONTAINER_BYTES / IMAGE_BYTES),
         "%d non-overlapping containers, %d of them packed; a byte-permuted image holds 0 packed"
         % (CONTAINERS, PACKED)),
        ("stored container header (kind 0)", "SAME", "23,304 B at file 0x000000B8",
         "kind 0, declared 23,296 B, the same file offset and header size as the other title"),
        ("tile banks named by a map root", "SAME",
         "%d banks = %d B declared, %d B stored" % (
             banks["map_banks"], banks["map_banks"] * banks["map_declared"],
             banks["map_stored"]),
         "every entry of the table at 0x084DF574 is kind 1 declaring %d B; the loader at "
         "0x0800510C reserves that many bytes, reads the table at root+0x4C (0x08005148) and "
         "decodes the container it names (0x0800514E)" % banks["map_declared"]),
        ("character tile banks", "DIFFERENT",
         "%d instances, %d B declared each, %d 4bpp tiles" % (
             banks["character_banks"], banks["character_declared"],
             banks["character_tiles"]),
         "the codec is the same and the granularity is not: the loader at 0x080072C4 takes its "
         "length from the container's declared size (0x080072EC) and its destination stride is "
         "one 32-byte tile, so a bank is as large as its own header says"),
        ("map container: root record", "SAME", "%d roots = %d B" % (
            map_counts["roots"], map_counts["roots"] * mapcontainer.ROOT_EXTENT),
         "0x50 B records with the four layer pointers at +0x14..+0x20 and the tile-bank table at "
         "+0x4C; reader 0x0800EB4C"),
        ("map container: dominant layer record", "SAME", "%d records = %d B, %d chunk pointers"
         % (map_counts["factories"],
            map_counts["record_bytes"] - map_counts["roots"] * mapcontainer.ROOT_EXTENT
            - map_counts["root_table_bytes"], map_counts["chunks"]),
         "counts at +0x14/+0x15 and the pointer array at +0x18; reader 0x080052FA..0x08005310; "
         "every chunk pointer is a container header"),
        ("map container: screenblock and terrain records", "DIFFERENT",
         "0 records of either shape",
         "%d of %d layer records carry a factory other than 0x%08X and no selector set picks "
         "their layout" % (map_counts["others"], map_counts["layers"], mapcontainer.FACTORY)),
        ("map container: root table", "SAME", "%d rows = %d B" % (
            map_counts["root_table_rows"], map_counts["root_table_bytes"]),
         "count at root+0x24, base at root+0x28, 24 B per row"),
        ("sprite asset directory", "PARTIAL", "%d entries, id %d: %d slots, %d distinct "
         "containers of %s B declared" % (
             asset["entries"], asset["definition_id"], asset["slots"], asset["containers"],
             ", ".join("%d" % value for value in asset["declared"])),
         "resolver 0x08009324 reads 0x%06X + 4*id and the slot array is at +0x%02X against the "
         "other title's +0x%02X; the 12-byte piece with its container pointer at +%d is that "
         "title's piece shape" % (asset_directory.TABLE, asset_directory.SLOT_FIELD,
                                  asset_directory.BF_SLOT_FIELD,
                                  asset_directory.PIECE_POINTER)),
        ("opcode stream", "DIFFERENT", "%d streams / %d B / %d instructions" % (
            streams["streams"], streams["bytes"], streams["instructions"]),
         "interpreter 0x080092E4, table 0x083B5C00 with 30 entries and a null at 0x11; every "
         "stream ends on 0x11 and re-emits its bytes"),
        ("opcode operand widths", "DIFFERENT", "%d instructions, all ends on 0x11" % (
            streams["instructions"],),
         "0x12, 0x13 and 0x1C take a one-byte offset; 0x02, 0x03 and 0x15..0x1A dispatch to a "
         "sub-table; the table stops at 0x1D where the other title's carries a 31st entry"),
        ("text storage", "PARTIAL",
         "%d strings / %d B inside a stored container, %d strings / %d B plain" % (
             text["roster"], text["roster_bytes"], text["objectives"],
             text["objective_bytes"]),
         "the draw routine at 0x0801F702 fetches a ONE-BYTE code (0x0801F718) and indexes the "
         "256-entry u16 table at 0x08028724 (0x0801F744); %d of %d roster strings lie inside "
         "one stored container, and the other title's strings are 16-bit code units"
         % (text["contained"], text["roster"])),
        ("wide-string table", "DIFFERENT",
         "%d printable 16-bit runs / %d B, none with a reader" % (WIDE_RUNS, WIDE_BYTES),
         "the string routine reads one-byte codes, so no 16-bit run is a string it can draw; the "
         "other title's 1,534-string table is 82,384 B"),
    ]


def doc_text(result):
    map_counts = result["map"][0]
    whole = result["map"][1]
    region = result["map"][2]
    streams = result["streams"]
    asset = result["asset"]
    banks = result["banks"]
    strings = result["text"]
    lines = []
    add = lines.append
    add("# Format reuse between Dragon Ball Z: The Legacy of Goku II and Buu's Fury")
    add("")
    add("Generated by `python tools\\research\\format_reuse.py --write`; `--check` re-derives this "
        "page from the builder's image and refuses a difference.")
    add("")
    add("Each verdict compares one format with the other title's grammar. `SAME` means the fields "
        "decode at the same offsets under the same reader. `DIFFERENT` names the first field that "
        "disagrees with its bytes and the instruction that reads it. The map container as a whole "
        "is `PARTIAL`: its root and dominant layer families are `SAME`, and the screenblock and "
        "terrain families have no member here, so the rows below split that container into its "
        "families rather than repeating one word for it.")
    add("")
    add("## Verdicts")
    add("")
    add("| format | verdict | measured | evidence |")
    add("|---|---|---|---|")
    for name, verdict, measured, evidence in verdict_rows(result):
        add("| %s | %s | %s | %s |" % (name, verdict, measured, evidence))
    add("")
    add("## The map container")
    add("")
    add("The chain is `MapEntry` table at file 0x409368, stride 0x38, field +0x2C naming a root "
        "pointer array; a root is a 0x50 B record whose +0x4C word is the tile-bank table "
        "0x084DF574. Measured: %d entries, %d roots, %d layer records. The root reader is at "
        "0x0800EB4C (`ldr r0,[r0,#0x2c]`, `lsls r1,r1,#2`, `adds r0,r0,r1`, `subs r0,#0x40`, "
        "`ldr r0,[r0,#0x3c]`), the same five-instruction shape the other title's map code uses."
        % (map_counts["entries"], map_counts["roots"], map_counts["layers"]))
    add("")
    add("The dominant layer record keeps that title's layout: factory word at +0x00, declared size "
        "at +0x04, the row and column counts as two bytes at +0x14 and +0x15, and the container "
        "array at +0x18. The reader at 0x08005300 passes the counts and the array: "
        "`ldrb r6,[r5,#0x14]`, `ldrb r0,[r5,#0x15]`, `muls r6,r0,r6`, `ldr r0,[r4,#8]`, "
        "`lsls r1,r5,#2`, `adds r0,r0,r1`, `ldr r0,[r0,#0x18]`. Measured: %d such records, %d "
        "distinct chunk pointers, every one a container header, %d B of declared payload."
        % (map_counts["factories"], map_counts["chunks"], map_counts["declared_payload"]))
    add("")
    add("The first disagreement is the factory word. %d of the %d layer records carry a word other "
        "than 0x%08X, and neither screenblock nor terrain record shape occurs: the other title "
        "dispatches on four handler words there, while this image calls the word as a constructor."
        % (map_counts["others"], map_counts["layers"], mapcontainer.FACTORY))
    add("")
    add("Record bytes: %d B in %d records (%d roots, %d dominant records, %d root-table rows)."
        % (map_counts["record_bytes"],
           map_counts["roots"] + map_counts["factories"] + map_counts["root_table_rows"],
           map_counts["roots"], map_counts["factories"], map_counts["root_table_rows"]))
    add("")
    add("Null: a byte-permuted image yields entries=%d roots=%d layers=%d, and a permutation of "
        "the image above the entry table yields entries=%d roots=%d layers=%d."
        % (whole["entries"], whole["roots"], whole["layers"],
           region["entries"], region["roots"], region["layers"]))
    add("")
    add("## The opcode streams")
    add("")
    add("The interpreter at 0x080092E4 reads one byte, increments the cursor, scales it by four "
        "and loads the entry from 0x083B5C00; a null entry ends the stream. Measured dispatch:")
    add("")
    for address, expected, text in opcode_stream.LOOP:
        add("- `0x%08X` `%s` `%s`" % (address, expected, text))
    add("")
    add("The table holds %d entries: 0x00..0x10 and 0x12..0x1D have handlers, 0x11 is the null."
        % opcode_stream.TABLE_ENTRIES)
    add("")
    add("| opcode | handler | operands |")
    add("|---|---|---|")
    for opcode in range(opcode_stream.TABLE_ENTRIES):
        if opcode == opcode_stream.END:
            add("| `0x%02X` | none | ends the stream |" % opcode)
            continue
        handler, kind, _quotes = opcode_stream.HANDLERS[opcode]
        add("| `0x%02X` | `0x%08X` | %s |" % (opcode, handler, opcode_stream.KIND_TEXT[kind]))
    add("")
    add("Against the other title's 31-handler grammar the skeleton is the same and the operands "
        "are not: 0x12, 0x13 and 0x1C carry a one-byte offset where that table carries two; 0x02, "
        "0x03 and 0x15..0x1A name a sub-opcode that 0x083B5D28 or 0x083B5F70 dispatches, where "
        "that table's handlers read a bare byte; and this table stops at 0x1D, a handler short.")
    add("")
    add("The streams are the 43 records of the objective table at file 0x6D68DC, stride 16, whose "
        "+0x04 and +0x08 words name two streams and whose +0x0C word names a text. Measured: %d "
        "streams, %d B, %d instructions, %d ending on 0x11, opcodes %s, sub-opcodes %s."
        % (streams["streams"], streams["bytes"], streams["instructions"], streams["ends"],
           sorted((hex(key), value) for key, value in streams["ops"].items()),
           sorted(((hex(pair[0]), hex(pair[1])), value)
                  for pair, value in streams["subs"].items())))
    add("")
    add("## The sprite asset directory")
    add("")
    add("The directory is a table of %d structure pointers from 0x%06X, after %d null words. The "
        "resolver at 0x08009324 reads entry `0x%06X + 4*id`, with the literal 0x%08X loaded at "
        "file 0x%X:"
        % (asset["entries"], asset_directory.TABLE, asset["null_slots"], asset_directory.TABLE,
           asset_directory.LITERAL_VALUE, asset_directory.LITERAL))
    add("")
    for address, halfword, text in asset_directory.QUOTE:
        add("- `0x%08X` `%s` `%s`" % (address, halfword, text))
    add("")
    add("Id %d resolves to the structure at 0x%08X: the count at +0x%02X is %d and the slot "
        "array is at +0x%02X. The first slot's record is a %d-byte piece `{s8 x, s8 y, u8 w, u8 "
        "h}` = %s at attribute 0x%08X, and its +%d word is 0x%08X, a kind-%d container declaring "
        "%d B that decodes to %d B. Its %d slots name %d distinct containers declaring %s B."
        % (asset["definition_id"], asset["definition"], asset_directory.COUNT_FIELD,
           asset["slots"], asset_directory.SLOT_FIELD, asset_directory.PIECE,
           asset["piece_box"], asset["piece_attribute"], asset_directory.PIECE_POINTER,
           asset["piece_container"], asset["kind"], asset["declared"][0], asset["payload"],
           asset["slots"], asset["containers"],
           ", ".join("%d" % value for value in asset["declared"])))
    add("")
    add("Against the other title: the pointer-table entry and the 12-byte piece whose +%d word "
        "is the container are the same shape; the slot array is +0x%02X against +0x%02X, the "
        "count is a u32 at +0x%02X against that title's low u16 at +0x00, and the table holds "
        "%d entries against %d. That title's slot names an animation record whose frames carry "
        "the pieces, a layer this image does not have at the slot."
        % (asset_directory.PIECE_POINTER, asset_directory.SLOT_FIELD,
           asset_directory.BF_SLOT_FIELD, asset_directory.COUNT_FIELD, asset["entries"],
           asset_directory.BF_ENTRIES))
    add("")
    add("## The tile banks")
    add("")
    add("The map loader reserves the map bank's %d B, reads the table from the root's +0x4C word "
        "and decodes the container the entry names:" % banks["map_declared"])
    add("")
    for address, hex_bytes, text in tilebank.MAP_LOADER:
        add("- `0x%08X` `%s` `%s`" % (address, hex_bytes, text))
    add("")
    add("The character path fixes its length from the container itself, not from a constant:")
    add("")
    for address, hex_bytes, text in tilebank.CHARACTER_LOADER:
        add("- `0x%08X` `%s` `%s`" % (address, hex_bytes, text))
    add("")
    add("Both paths hand the container to the same dispatcher, which reads the kind and the "
        "payload from the header:")
    add("")
    for address, hex_bytes, text in tilebank.DECODER:
        add("- `0x%08X` `%s` `%s`" % (address, hex_bytes, text))
    add("")
    add("Measured: %d map banks, %d B declared each, %d B stored over a %d B span with %d B of "
        "gaps; %d character instances of %d B. A shuffle of the whole image and a shuffle of the "
        "bank block alone decode %d and %d banks."
        % (banks["map_banks"], banks["map_declared"], banks["map_stored"], banks["map_span"],
           banks["map_span"] - banks["map_stored"], banks["character_banks"],
           banks["character_declared"], banks["null_whole"], banks["null_region"]))
    add("")
    add("## The text")
    add("")
    add("The string routine at 0x0801F702 fetches one byte, skips a leading space, and turns the "
        "code into a record offset and then into that record's width:")
    add("")
    for address, hex_bytes, text in text_storage.DRAW:
        add("- `0x%08X` `%s` `%s`" % (address, hex_bytes, text))
    add("")
    add("The advance is the record's width plus one. The table at 0x%06X holds %d defined codes "
        "and as many records. Measured: %d pointers name %d distinct strings of %d B inside the "
        "stored container at 0x%06X, and %d strings of %d B lie outside it. A shuffle of the whole "
        "image and a shuffle of the container's payload resolve %d and %d strings."
        % (text_storage.FONT_TABLE, strings["codes"], strings["roster_pointers"],
           strings["roster"], strings["roster_bytes"], text_storage.TEXT_CONTAINER,
           strings["objectives"], strings["objective_bytes"], strings["null_whole"],
           strings["null_region"]))
    add("")
    add("Against the other title: the record shape is the same (a record offset table, a u16 "
        "width, columns, advance = width + 1) and the code width is not, one byte here against "
        "that title's 16-bit code units, so a wide-string table has no member on this image.")
    add("")
    add("## Formats measured before this page")
    add("")
    add("The container census is quoted from the earlier cross-title measurement, which ran the "
        "other title's decoders unchanged on this image: %d non-overlapping containers covering "
        "%d B, %d of them packed, and a byte-permuted image with 0 packed. The tile banks and the "
        "text are now read by the two tools below."
        % (CONTAINERS, CONTAINER_BYTES, PACKED))
    add("")
    add("## The table at 0x086A3580")
    add("")
    add("Sixteen consecutive in-image pointers at 0x086A3580 look like a handler table and are "
        "not one. The layer record at 0x086A3548 carries factory 0x%08X, a declared size of 0x400 "
        "at +0x04, the counts 5 and 5 at +0x14 and +0x15, and a 25-entry container array from "
        "0x086A3560; 0x086A3580 is entry 8 of that array. Each entry is a kind-1 container "
        "declaring 0x800 B, so the run is a slice of a map layer's payload list."
        % mapcontainer.FACTORY)
    add("")
    add("## Reproduce")
    add("")
    add("    python tools\\mapcontainer\\mapcontainer.py --check")
    add("    python tools\\research\\opcode_stream.py --check")
    add("    python tools\\tilebank\\tilebank.py --check")
    add("    python tools\\text\\text_storage.py --check")
    add("    python tools\\research\\format_reuse.py --check")
    add("")
    return "\n".join(lines) + "\n"


def write_doc(text):
    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with open(DOC, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def check_doc(text):
    if not os.path.exists(DOC):
        print("FORMAT FAIL: %s is absent" % os.path.basename(DOC))
        return 1
    if open(DOC, encoding="utf-8", newline="").read() != text:
        print("FORMAT FAIL: %s is not what this image derives" % os.path.basename(DOC))
        return 1
    print("FORMAT PASS")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--write"], ["--check"]):
        print("usage: python tools\\research\\format_reuse.py [--write|--check]")
        return 2
    if not os.path.exists(ROM):
        print("the format census needs the retail image at %s" % ROM)
        return 1
    image = open(ROM, "rb").read()
    if hashlib.sha256(image).hexdigest() != ROM_SHA256:
        print("the image at %s is not the canonical image" % ROM)
        return 1
    result = measure(image)
    text = doc_text(result)
    if argv == ["--write"]:
        write_doc(text)
        print("wrote %s" % os.path.basename(DOC))
        return 0
    if argv == ["--check"]:
        return check_doc(text)
    for name, verdict, measured, _evidence in verdict_rows(result):
        print("%-46s %-10s %s" % (name, verdict, measured))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
