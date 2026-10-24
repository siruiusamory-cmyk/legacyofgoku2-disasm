from __future__ import annotations

import bisect
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "code"))
sys.path.insert(0, os.path.join(ROOT, "tools", "maprecords"))
sys.path.insert(0, os.path.join(ROOT, "tools", "sprites"))
sys.path.insert(0, os.path.join(ROOT, "tools", "text"))
sys.path.insert(0, HERE)

import container
import container_census
import emit_code
import jcalg1
import maprecords
import sprites
import text_rows

ROM = os.path.join(ROOT, "baserom.gba")
ASM = os.path.join(ROOT, "asm", "remainder.s")
OUT = os.path.join(ROOT, "build", "jcalg1")
CACHE = os.path.join(ROOT, "build", "compress-cache")
ROM_BASE = 0x08000000
START = 0x100
END = 0x800000
MAX_OUTPUT = 0x40000
ENCODER_BLOCK_HEADER = 10
INCLUDED_KIND = 2
GEN = re.compile(r"build\\jcalg1\\gen_([0-9a-f]+)_([0-9a-f]+)\.bin$")
MAP = re.compile(r"build\\maprecords\\rec_([0-9a-f]+)_([0-9a-f]+)\.bin$")
SPRITE = re.compile(r"build\\sprites\\rec_([0-9a-f]+)_([0-9a-f]+)\.bin$")
TEXT = re.compile(r"build\\text\\rec_([0-9a-f]+)_([0-9a-f]+)\.bin$")
GAP = re.compile(r"baserom\.gba_0x([0-9a-f]+)_0x([0-9a-f]+)\.extracted$")
INCLUDE = re.compile(r"\.\.\\build\\code\\[A-Za-z0-9_]+\.s$")
INCBIN = re.compile(r"INCBIN\s+(\S+)")


def gap_name(start, end):
    return "baserom.gba_0x%x_0x%x.extracted" % (start, end)


def run_name(start, end):
    return "build\\jcalg1\\gen_%x_%x.bin" % (start, end)


def tokens_of(runs, code=(), record_runs=()):
    starts = [start for start, _end in runs]

    def inside_run(start, end):
        index = bisect.bisect_left(starts, end) - 1
        return index >= 0 and runs[index][0] <= start and end <= runs[index][1]

    pieces = [(start, end, run_name(start, end)) for start, end in runs]
    pieces += [(start, end, token) for start, end, token in code
               if not inside_run(start, end)]
    pieces += [(start, end, token) for start, end, token in record_runs]
    pieces.sort()
    tokens = []
    cursor = START
    for start, end, token in pieces:
        if start < cursor:
            raise ValueError("token 0x%X starts inside the previous token 0x%X" % (start, cursor))
        if start > cursor:
            tokens.append(gap_name(cursor, start))
        tokens.append(token)
        cursor = end
    if cursor < END:
        tokens.append(gap_name(cursor, END))
    return tokens


def code_tokens(image):
    result = emit_code.fragments(image)
    return [(begin - ROM_BASE, end - ROM_BASE, "..\\build\\code\\" + name)
            for begin, end, name in emit_code.span_files(result)]


def record_tokens(image):
    return maprecords.tokens(image) + sprites.tokens(image) + text_rows.tokens(image)


def asm_text(tokens):
    lines = ["\tAREA\tRemainder, CODE, READONLY"]
    for token in tokens:
        directive = "INCLUDE" if INCLUDE.search(token) else "INCBIN"
        lines.append("\t\t%s\t%s" % (directive, token))
    return "\n".join(lines) + "\n"


def parsed_asm(text):
    tokens = []
    for match in INCBIN.finditer(text):
        token = match.group(1)
        found = (GEN.search(token) or MAP.search(token) or SPRITE.search(token)
                 or TEXT.search(token))
        if found:
            start, end = (int(found.group(index), 16) for index in (1, 2))
            if end <= start:
                raise ValueError("%s ends at 0x%X, not past its start 0x%X" % (token, end, start))
            tokens.append((start, end, token))
            continue
        found = GAP.search(token)
        if not found:
            raise ValueError("%s is neither a generated run nor a retail gap" % token)
        start, end = (int(found.group(index), 16) for index in (1, 2))
        tokens.append((start, end, token))
    tokens.sort()
    return tokens


def payload_of(image, offset):
    return container.unpack(image, offset, maximum_output=MAX_OUTPUT).data


def encoded(payload, store):
    digest = hashlib.sha256(payload).hexdigest()
    path = os.path.join(CACHE, digest)
    if os.path.exists(path):
        with open(path, "rb") as handle:
            blob = handle.read()
        if len(blob) >= 8:
            kind, declared = (int.from_bytes(blob[index:index + 4], "little") for index in (0, 4))
            if kind == jcalg1.PACKED_KIND and declared == len(payload):
                return blob, True
    blob = jcalg1.encode(payload)
    if store:
        os.makedirs(CACHE, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(blob)
    return blob, False


def measure(image, store):
    real = container_census.summarise(image, lambda payload: encoded(payload, store)[0])
    accepted = sorted(real["accepted"], key=lambda item: item["offset"])
    following = {}
    for index, hit in enumerate(accepted):
        following[hit["offset"]] = (accepted[index + 1]["offset"]
                                    if index + 1 < len(accepted) else END)
    exact, left = [], []
    reasons = {}
    misses = trusted = shared = 0
    for hit in real["packed"]:
        if hit["offset"] < START or hit["offset"] + hit["packed"] > END:
            reason = "outside the remainder"
        else:
            payload = payload_of(image, hit["offset"])
            if len(payload) < ENCODER_BLOCK_HEADER:
                reason = "shorter than the encoder's header"
            else:
                blob, was_cached = encoded(payload, store)
                if hit["kind"] == INCLUDED_KIND:
                    blob = hit["kind"].to_bytes(4, "little") + blob[4:]
                extent = len(blob)
                if hit["kind"] not in (jcalg1.PACKED_KIND, INCLUDED_KIND):
                    reason = "kind %d" % hit["kind"]
                elif extent < hit["packed"]:
                    reason = "shorter than the decoded extent"
                elif image[hit["offset"]:hit["offset"] + extent] != blob:
                    reason = "no byte equality"
                else:
                    if hit["offset"] + extent > following[hit["offset"]]:
                        extent = following[hit["offset"]] - hit["offset"]
                        shared += 1
                    reason = None
        if reason is None:
            exact.append(dict(hit, extent=extent))
            trusted += 1 if was_cached else 0
            misses += 0 if was_cached else 1
        else:
            left.append(dict(hit, reason=reason))
            reasons[reason] = reasons.get(reason, 0) + 1
    runs = []
    for hit in exact:
        end = hit["offset"] + hit["extent"]
        if runs and runs[-1][1] == hit["offset"]:
            runs[-1][1] = end
        else:
            runs.append([hit["offset"], end])
    return {"exact": exact, "left": left, "reasons": sorted(reasons.items()),
            "runs": [tuple(run) for run in runs], "misses": misses, "trusted": trusted,
            "shared": shared}


def reason_text(result):
    return " ".join("%s=%d" % (name.replace(" ", "-"), count)
                    for name, count in result["reasons"])


def write_asm(tokens):
    os.makedirs(os.path.dirname(ASM), exist_ok=True)
    with open(ASM, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(asm_text(tokens))


def run_bytes(image, start, end):
    blob = bytearray()
    count = 0
    offset = start
    while offset < end:
        if not container.looks_like_container(image, offset):
            raise ValueError("0x%X is not a container header inside the run 0x%X..0x%X"
                             % (offset, start, end))
        unpacked = container.unpack(image, offset, maximum_output=MAX_OUTPUT)
        encoded_blob, _cached = encoded(unpacked.data, True)
        if unpacked.kind == INCLUDED_KIND:
            encoded_blob = unpacked.kind.to_bytes(4, "little") + encoded_blob[4:]
        extent = min(len(encoded_blob), end - offset)
        if image[offset:offset + len(encoded_blob)] != encoded_blob:
            raise ValueError("the re-encoded container at 0x%X is not the image's bytes" % offset)
        blob += encoded_blob[:extent]
        count += 1
        offset += extent
    if offset != end:
        raise ValueError("the containers of 0x%X..0x%X end at 0x%X" % (start, end, offset))
    return bytes(blob), count


def build(image):
    text = open(ASM, encoding="utf-8", newline="").read()
    tokens = parsed_asm(text)
    os.makedirs(OUT, exist_ok=True)
    runs = 0
    containers = 0
    for start, end, token in tokens:
        if MAP.search(token) or SPRITE.search(token) or TEXT.search(token):
            if not os.path.exists(os.path.join(ROOT, token)):
                raise ValueError("%s is absent" % token)
            continue
        if GEN.search(token):
            blob, count = run_bytes(image, start, end)
            path = os.path.join(ROOT, token)
            with open(path, "wb") as handle:
                handle.write(blob)
            if open(path, "rb").read() != blob:
                raise ValueError("%s does not hold 0x%X..0x%X" % (path, start, end))
            runs += 1
            containers += count
        else:
            path = os.path.join(ROOT, token)
            with open(path, "wb") as handle:
                handle.write(image[start:end])
            if os.path.getsize(path) != end - start:
                raise ValueError("%s does not hold 0x%X..0x%X" % (path, start, end))
    return tokens, runs, containers


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in ([], ["--write"], ["--check"]):
        print("usage: python tools\\compress\\generate_containers.py [--write|--check]")
        return 2
    if not os.path.exists(ROM):
        print("the container generator needs the retail image at %s" % ROM)
        return 1
    image = open(ROM, "rb").read()
    if hashlib.sha256(image).hexdigest() != container_census.ROM_SHA256:
        print("the image at %s is not the canonical image" % ROM)
        return 1
    if argv == ["--check"]:
        result = measure(image, False)
        tokens = tokens_of(result["runs"], code_tokens(image), record_tokens(image))
        if not os.path.exists(ASM):
            print("CONTAINERS FAIL: %s is absent" % os.path.basename(ASM))
            return 1
        if open(ASM, encoding="utf-8", newline="").read() != asm_text(tokens):
            print("CONTAINERS FAIL: %s is not what this image derives" % os.path.basename(ASM))
            return 1
        print("CONTAINERS PASS containers=%d runs=%d moved=%d left=%d %s end-marker-shared=%d"
              % (len(result["exact"]), len(result["runs"]),
                 sum(hit["extent"] for hit in result["exact"]), len(result["left"]),
                 reason_text(result), result["shared"]))
        return 0
    if argv == ["--write"]:
        result = measure(image, True)
        tokens = tokens_of(result["runs"], code_tokens(image), record_tokens(image))
        write_asm(tokens)
        print("wrote %s containers=%d runs=%d moved=%d left=%d %s end-marker-shared=%d "
              "encode misses=%d trusted=%d"
              % (os.path.basename(ASM), len(result["exact"]), len(result["runs"]),
                 sum(hit["extent"] for hit in result["exact"]), len(result["left"]),
                 reason_text(result), result["shared"], result["misses"], result["trusted"]))
    else:
        result = measure(image, True)
        tokens = tokens_of(result["runs"], code_tokens(image), record_tokens(image))
        if not os.path.exists(ASM):
            print("CONTAINERS FAIL: %s is absent" % os.path.basename(ASM))
            return 1
        if open(ASM, encoding="utf-8", newline="").read() != asm_text(tokens):
            print("CONTAINERS FAIL: %s is not what this image derives" % os.path.basename(ASM))
            return 1
        print("containers=%d runs=%d moved=%d left=%d %s end-marker-shared=%d encode misses=%d "
              "trusted=%d"
              % (len(result["exact"]), len(result["runs"]),
                 sum(hit["extent"] for hit in result["exact"]), len(result["left"]),
                 reason_text(result), result["shared"], result["misses"], result["trusted"]))
    parsed, runs, containers = build(image)
    print("tokens=%d runs=%d containers=%d" % (len(parsed), runs, containers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
