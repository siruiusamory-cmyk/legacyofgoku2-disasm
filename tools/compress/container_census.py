from __future__ import annotations

import bisect
import csv
import hashlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "compress"))
sys.path.insert(0, os.path.join(ROOT, "tools", "mapcontainer"))

import container
import jcalg1
import mapcontainer

ROM = os.path.join(ROOT, "baserom.gba")
DOC = os.path.join(ROOT, "tools", "compress", "CONTAINER_CENSUS.md")
CSV = os.path.join(ROOT, "tools", "compress", "CONTAINER_CENSUS.csv")
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
IMAGE_BYTES = 8388608
MAX_OUTPUT = 0x40000
STEP = 4
NULL_BLOCK = 0x10000
ENCODER_BLOCK_HEADER = 10
INCLUDED_KIND = 2
PINNED = {"accepted": 13913, "packed": 9919, "stored": 3994, "union_bytes": 4775808,
          "rejected": 1256, "recovered": 3631,
          "null_accepted": 187, "null_packed": 0}


def digest16(data):
    return hashlib.sha256(data).hexdigest().upper()[:16]


def shape_of(length):
    if length and length % 0x1000 == 0:
        return "0x1000-multiple"
    if length and length % 64 == 0:
        return "64-multiple"
    if length and length % 32 == 0:
        return "32-multiple"
    return "other"


def hits(image):
    found = []
    for offset in range(0, len(image) - 8, STEP):
        if not container.looks_like_container(image, offset):
            continue
        kind, declared = container.read_header(image, offset)
        try:
            unpacked = container.unpack(image, offset, maximum_output=MAX_OUTPUT)
        except container.ContainerError as error:
            found.append({"offset": offset, "kind": kind, "declared": declared, "ok": False,
                          "reason": str(error)[:40]})
            continue
        found.append({"offset": offset, "kind": kind, "declared": declared, "ok": True,
                      "packed": unpacked.packed_size, "payload": len(unpacked.data),
                      "digest": digest16(unpacked.data), "shape": shape_of(len(unpacked.data))})
    return found


def merged_spans(hits):
    spans = []
    for start, end in sorted((hit["offset"], hit["offset"] + hit["packed"]) for hit in hits):
        if spans and start <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return spans


def overlaps(spans, starts, begin, end):
    index = bisect.bisect_left(starts, end) - 1
    return index >= 0 and spans[index][1] > begin


def reencodes(image, hit, encode):
    payload = container.unpack(image, hit["offset"], maximum_output=MAX_OUTPUT).data
    if len(payload) < ENCODER_BLOCK_HEADER:
        return False
    blob = encode(payload)
    if hit["kind"] == INCLUDED_KIND:
        blob = hit["kind"].to_bytes(4, "little") + blob[4:]
    return (len(blob) >= hit["packed"]
            and image[hit["offset"]:hit["offset"] + len(blob)] == blob)


def recoverable(image, good, chunks, encode):
    by_offset = {hit["offset"]: hit for hit in good}
    return [by_offset[offset] for offset in chunks
            if offset in by_offset and by_offset[offset]["kind"] != container.STORED
            and reencodes(image, by_offset[offset], encode)]


def greedy(found):
    accepted = []
    edge = -1
    for hit in sorted(found, key=lambda item: item["offset"]):
        if hit["offset"] < edge:
            continue
        accepted.append(hit)
        edge = hit["offset"] + hit["packed"]
    return accepted


def population(good, recovered):
    accepted = greedy(good)
    taken = {hit["offset"] for hit in accepted}
    recovered = [hit for hit in recovered if hit["offset"] not in taken]
    spans = merged_spans(recovered)
    starts = [span[0] for span in spans]
    kept, rejected = [], []
    for hit in accepted:
        if hit["kind"] == container.STORED and overlaps(
                spans, starts, hit["offset"], hit["offset"] + hit["packed"]):
            rejected.append(hit)
            continue
        kept.append(hit)
    return (sorted(kept + recovered, key=lambda item: item["offset"]), rejected, recovered)


def union_bytes(accepted, length):
    marks = bytearray(length)
    for hit in accepted:
        marks[hit["offset"]:hit["offset"] + hit["packed"]] = b"\x01" * hit["packed"]
    return sum(marks)


def permute(image):
    out = bytearray(image)
    for base in range(0, len(out), NULL_BLOCK):
        block = out[base:base + NULL_BLOCK]
        halfwords = [block[index:index + 2] for index in range(0, len(block) - 1, 2)]
        halfwords.reverse()
        for index, pair in enumerate(halfwords):
            out[base + 2 * index:base + 2 * index + 2] = pair
    return bytes(out)


def summarise(image, encode=None, chunks=None):
    encode = jcalg1.encode if encode is None else encode
    chunks = mapcontainer.chunk_pointers(image) if chunks is None else chunks
    found = hits(image)
    good = [hit for hit in found if hit["ok"]]
    refused = [hit for hit in found if not hit["ok"]]
    accepted, rejected, recovered = population(
        good, recoverable(image, good, chunks, encode))
    kinds = {}
    sizes = {}
    shapes = {}
    for hit in accepted:
        kinds[hit["kind"]] = kinds.get(hit["kind"], 0) + 1
        sizes[hit["declared"]] = sizes.get(hit["declared"], 0) + 1
        shapes[hit["shape"]] = shapes.get(hit["shape"], 0) + 1
    stored = [hit for hit in accepted if hit["kind"] == container.STORED]
    packed = [hit for hit in accepted if hit["kind"] != container.STORED]
    union = union_bytes(accepted, len(image))
    return {"bytes": len(image), "hits": len(found), "decoded": len(good),
            "refused": len(refused), "accepted": accepted, "kinds": sorted(kinds.items()),
            "stored": stored, "packed": packed, "stored_over": len(rejected),
            "raised": len(recovered), "stored_bytes": sum(hit["packed"] for hit in stored),
            "packed_bytes": sum(hit["packed"] for hit in packed),
            "payload_bytes": sum(hit["payload"] for hit in accepted),
            "union_bytes": union, "sizes": sorted(sizes.items(), key=lambda pair: -pair[1])[:8],
            "shapes": sorted(shapes.items())}


def first_row(label, group):
    if not group:
        return "-"
    hit = group[0]
    return ("kind %d, declared %d B, packed %d B, payload %d B, payload sha256[:16] %s"
            % (hit["kind"], hit["declared"], hit["packed"], hit["payload"], hit["digest"]))


def doc_text(real, null):
    lines = []
    add = lines.append
    add("# The JCALG1 container population")
    add("")
    add("Generated by `python tools\\compress\\container_census.py --write`; `--check` re-derives "
        "this page and its CSV from the builder's image and refuses a difference.")
    add("")
    add("## Method")
    add("")
    add("The scan reads every 4-byte-aligned site in the image. A site is a container when its "
        "first word is a kind in 0, 1 or 2 and its second word is a declared size from 1 to "
        "65,536 B. A kind-0 container is its 8-byte header and that many stored bytes; kinds 1 "
        "and 2 decode the JCALG1 body against the declared size and end at the body's own end "
        "code. The accepted population is the greedy left-to-right set: a hit is accepted when "
        "its offset is at or past the end of the previous accepted hit, so no accepted extents "
        "overlap and the byte union is the sum of the packed extents.")
    add("")
    add("One group is removed from that selection. A kind-0 hit whose extent overlaps a "
        "container the map layer chunk directory names, which decodes and re-encodes to the "
        "image's own bytes, is rejected: the stored kind is an identity copy of the bytes under "
        "it, and that chunk is the source those bytes have. The chunk itself is accepted, and "
        "nothing else in the selection moves. Measured here: %d stored hits are rejected and %d "
        "chunks are recovered." % (real["stored_over"], real["raised"]))
    add("")
    add("The null permutes the image by reversing the halfword order inside every 64 KiB block, "
        "then runs the same scan and the same selection. A format found at this rate in the real "
        "image and absent from the null is measured, not fitted.")
    add("")
    add("A packed extent is the body's consumed input. When a body's output completes exactly on "
        "a 4-byte boundary the decoder stops there, so the stream's end-marker word falls in the "
        "following gap; a re-encoder emits that word, and a container's encoder extent can be "
        "one word longer than the extent this census records. Where that word is the bytes the "
        "next token already carries, the generator emits the container to the decoder's extent "
        "and the next token supplies the word.")
    add("")
    add("## Totals")
    add("")
    add("| measure | image | null |")
    add("|---|---|---|")
    add("| shape hits | %d | %d |" % (real["hits"], null["hits"]))
    add("| decoded | %d | %d |" % (real["decoded"], null["decoded"]))
    add("| refused | %d | %d |" % (real["refused"], null["refused"]))
    add("| non-overlapping accepted | %d | %d |" % (len(real["accepted"]), len(null["accepted"])))
    add("| stored (kind 0) | %d | %d |" % (len(real["stored"]), len(null["stored"])))
    add("| packed (kinds 1, 2) | %d | %d |" % (len(real["packed"]), len(null["packed"])))
    add("| packed extents | %d B | %d B |" % (real["packed_bytes"], null["packed_bytes"]))
    add("| stored extents | %d B | %d B |" % (real["stored_bytes"], null["stored_bytes"]))
    add("| declared payload | %d B | %d B |" % (real["payload_bytes"], null["payload_bytes"]))
    add("| byte union | %d B (%.1f %% of the image) | %d B (%.1f %%)"
        % (real["union_bytes"], 100.0 * real["union_bytes"] / real["bytes"],
           null["union_bytes"], 100.0 * null["union_bytes"] / null["bytes"]))
    add("| kinds | %s | %s |"
        % (", ".join("%d: %d" % pair for pair in real["kinds"]),
           ", ".join("%d: %d" % pair for pair in null["kinds"])))
    add("")
    add("The images share their scan, their decoder and their selection; only the bytes differ. "
        "The null holds %d packed containers against the image's %d, so the packed grammar is "
        "measured in the image and not manufactured by the scan."
        % (len(null["packed"]), len(real["packed"])))
    add("")
    add("## First accepted containers")
    add("")
    add("| group | first member |")
    add("|---|---|")
    add("| stored | %s |" % first_row("stored", real["stored"]))
    add("| packed | %s |" % first_row("packed", real["packed"]))
    add("")
    add("## Declared sizes")
    add("")
    add("The eight most frequent declared sizes in the accepted population: %s."
        % ", ".join("%d B x %d" % (size, count) for size, count in real["sizes"]))
    add("")
    add("Payload shapes: %s."
        % ", ".join("%s x %d" % (shape, count) for shape, count in real["shapes"]))
    add("")
    add("## The per-row ledger")
    add("")
    add("`tools/compress/CONTAINER_CENSUS.csv` carries one row per accepted container: offset, "
        "kind, declared size, packed extent, decoded length, payload shape and the first 16 hex "
        "digits of the decoded payload's sha256. The rows are the population the totals count.")
    add("")
    add("## Reproduce")
    add("")
    add("    python tools\\compress\\container_census.py --check")
    add("")
    return "\n".join(lines) + "\n"


def csv_text(real):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["offset", "kind", "declared", "packed", "payload", "shape",
                     "payload_sha256_16"])
    for hit in real["accepted"]:
        writer.writerow(["0x%06X" % hit["offset"], hit["kind"], hit["declared"], hit["packed"],
                         hit["payload"], hit["shape"], hit["digest"]])
    return out.getvalue()


def write_files(real, null):
    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    with open(DOC, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(doc_text(real, null))
    with open(CSV, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(csv_text(real))


def check_files(real, null):
    for path, text in ((DOC, doc_text(real, null)), (CSV, csv_text(real))):
        if not os.path.exists(path):
            print("CENSUS FAIL: %s is absent" % os.path.basename(path))
            return 1
        if open(path, encoding="utf-8", newline="").read() != text:
            print("CENSUS FAIL: %s is not what this image derives" % os.path.basename(path))
            return 1
    print("CENSUS PASS")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--write"], ["--check"], ["--null"]):
        print("usage: python tools\\compress\\container_census.py [--write|--check|--null]")
        return 2
    if not os.path.exists(ROM):
        print("the container census needs the retail image at %s" % ROM)
        return 1
    image = open(ROM, "rb").read()
    if hashlib.sha256(image).hexdigest() != ROM_SHA256:
        print("the image at %s is not the canonical image" % ROM)
        return 1
    chunks = mapcontainer.chunk_pointers(image)
    real = summarise(image, chunks=chunks)
    if argv == ["--null"]:
        null = summarise(permute(image), chunks=chunks)
        print("image containers=%d packed=%d packed_bytes=%d union=%d"
              % (len(real["accepted"]), len(real["packed"]), real["packed_bytes"],
                 real["union_bytes"]))
        print("null  containers=%d packed=%d packed_bytes=%d union=%d"
              % (len(null["accepted"]), len(null["packed"]), null["packed_bytes"],
                 null["union_bytes"]))
        return 0
    null = summarise(permute(image), chunks=chunks)
    if argv == ["--write"]:
        write_files(real, null)
        print("wrote %s and %s" % (os.path.basename(DOC), os.path.basename(CSV)))
    elif argv == ["--check"]:
        return check_files(real, null)
    print("containers=%d stored=%d packed=%d packed_bytes=%d declared_payload=%d "
          "union=%d (%.1f %%)"
          % (len(real["accepted"]), len(real["stored"]), len(real["packed"]),
             real["packed_bytes"], real["payload_bytes"], real["union_bytes"],
             100.0 * real["union_bytes"] / real["bytes"]))
    print("stored hits rejected=%d chunks recovered=%d"
          % (real["stored_over"], real["raised"]))
    print("null containers=%d packed=%d packed_bytes=%d"
          % (len(null["accepted"]), len(null["packed"]), null["packed_bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
