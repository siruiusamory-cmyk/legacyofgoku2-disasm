from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)

import container
import generate_containers
import jcalg1
import testkit

SHORT_CONTAINER = 0x0B8B84
SEAM_CONTAINER = 0x1D91EC
SEAM_RUN = (0x1D918C, 0x1D94D0)
SEAM_MARKER = 0x1D9230
KIND_TWO_CONTAINERS = 93
KIND_TWO_BYTES = 97272


def test_the_tracked_token_list_is_what_the_image_derives():
    testkit.rom_bytes(generate_containers.ROM,
                      digest=generate_containers.container_census.ROM_SHA256)
    assert generate_containers.main(["--check"]) == 0


def test_the_end_marker_word_a_container_shares_with_the_next_header_is_emitted_once():
    image = testkit.rom_bytes(generate_containers.ROM,
                              digest=generate_containers.container_census.ROM_SHA256)
    unpacked = container.unpack(image, SEAM_CONTAINER,
                                maximum_output=generate_containers.MAX_OUTPUT)
    encoded = jcalg1.encode(unpacked.data)
    assert unpacked.packed_end == SEAM_MARKER
    assert len(encoded) == unpacked.packed_size + 4
    assert encoded[unpacked.packed_size:] == b"\x00\x00\x00\x00"
    assert image[SEAM_MARKER:SEAM_MARKER + 4] == encoded[unpacked.packed_size:]
    assert container.read_header(image, SEAM_MARKER) == (container.STORED, 1)
    tokens = generate_containers.parsed_asm(
        open(generate_containers.ASM, encoding="utf-8").read())
    position = next(index for index, token in enumerate(tokens) if token[0] == SEAM_RUN[0])
    assert tokens[position][1] == SEAM_RUN[1]
    assert generate_containers.GEN.search(tokens[position][2]) is not None
    assert tokens[position + 1][0] == SEAM_RUN[1]
    assert generate_containers.GEN.search(tokens[position + 1][2]) is None
    blob, count = generate_containers.run_bytes(image, *SEAM_RUN)
    assert blob == image[SEAM_RUN[0]:SEAM_RUN[1]]
    assert len(blob) == 836 and count == 13


def test_every_kind_two_stream_is_emitted_with_its_kind_word_and_the_retail_body():
    image = testkit.rom_bytes(generate_containers.ROM,
                              digest=generate_containers.container_census.ROM_SHA256)
    hits = [hit for hit in generate_containers.container_census.summarise(image)["packed"]
            if hit["kind"] == 2]
    assert len(hits) == KIND_TWO_CONTAINERS
    assert sum(hit["packed"] for hit in hits) == KIND_TWO_BYTES
    tokens = generate_containers.parsed_asm(
        open(generate_containers.ASM, encoding="utf-8").read())
    for hit in hits:
        unpacked = container.unpack(image, hit["offset"],
                                    maximum_output=generate_containers.MAX_OUTPUT)
        blob, _cached = generate_containers.encoded(unpacked.data, False)
        patched = hit["kind"].to_bytes(4, "little") + blob[4:]
        assert image[hit["offset"]:hit["offset"] + len(patched)] == patched
        covering = [token for start, end, token in tokens if start <= hit["offset"] < end]
        assert covering and generate_containers.GEN.search(covering[0]) is not None


def test_a_payload_below_the_encoder_header_is_left_without_reaching_the_encoder(monkeypatch):
    image = testkit.rom_bytes(generate_containers.ROM,
                              digest=generate_containers.container_census.ROM_SHA256)
    unpacked = container.unpack(image, SHORT_CONTAINER, maximum_output=generate_containers.MAX_OUTPUT)
    assert len(unpacked.data) < generate_containers.ENCODER_BLOCK_HEADER
    short = bytearray(b"\xff" * 0x200)
    at = generate_containers.START + 0x10
    short[at:at + unpacked.packed_size] = image[SHORT_CONTAINER:SHORT_CONTAINER + unpacked.packed_size]
    monkeypatch.setattr(jcalg1, "COMPRESS", os.path.join(HERE, "absent-encoder.exe"))
    for _ in range(20):
        result = generate_containers.measure(bytes(short), False)
        assert [(hit["offset"], hit["reason"]) for hit in result["left"]] == [
            (at, "shorter than the encoder's header")]
        assert result["exact"] == [] and result["runs"] == []
        assert (result["misses"], result["trusted"]) == (0, 0)
