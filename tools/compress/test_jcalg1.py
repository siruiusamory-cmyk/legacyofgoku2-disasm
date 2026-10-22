from __future__ import annotations

import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)

import container
import jcalg1
import testkit

ROM = os.path.join(ROOT, "baserom.gba")
ROM_SHA256 = "6e6c370c339ec9171cb1956adf837a0d342a197f78964882ef46c3086656ff75"
PACKED_CONTAINER = 0x29294
PACKED_DECLARED = 38400
PACKED_EXTENT = 14800
PACKED_PAYLOAD_SHA256_16 = "03A04549D373470F"
WIDE_CONTAINER = 0x7065F4
WIDE_DECLARED = 38400


class Writer:

    def __init__(self):
        self._bits = []

    def put(self, value, width):
        for shift in range(width - 1, -1, -1):
            self._bits.append((value >> shift) & 1)

    def gamma(self, value):
        for shift in range(value.bit_length() - 2, -1, -1):
            self.put((value >> shift) & 1, 1)
            self.put(0 if shift == 0 else 1, 1)

    def finish(self):
        bits = self._bits + [0] * ((-len(self._bits)) % 32)
        out = bytearray()
        for start in range(0, len(bits), 32):
            word = 0
            for bit in bits[start:start + 32]:
                word = (word << 1) | bit
            out += struct.pack("<I", word)
        return bytes(out)


def container_at(body, declared):
    return struct.pack("<II", jcalg1.PACKED_KIND, declared) + body


def raw_run(blocks):
    writer = Writer()
    writer.put(0b001, 3)
    writer.put(0, 4)
    writer.put(1, 1)
    for index, block in enumerate(blocks):
        for value in block:
            writer.put(value, 8)
        writer.put(1 if index + 1 < len(blocks) else 0, 1)
    writer.put(0, 12)
    return writer.finish()


def test_the_retail_container_re_encodes_byte_for_byte():
    image = testkit.rom_bytes(ROM, digest=ROM_SHA256)
    unpacked = container.unpack(image, PACKED_CONTAINER, maximum_output=0x40000)
    assert (unpacked.kind, unpacked.declared_size, unpacked.packed_size) == (
        jcalg1.PACKED_KIND, PACKED_DECLARED, PACKED_EXTENT)
    assert hashlib.sha256(unpacked.data).hexdigest().upper()[:16] == PACKED_PAYLOAD_SHA256_16
    decoded, consumed = jcalg1.decompress(image, PACKED_CONTAINER + 8,
                                          PACKED_CONTAINER + PACKED_EXTENT)
    assert decoded == unpacked.data
    assert consumed == PACKED_EXTENT - 8
    blob = jcalg1.encode(unpacked.data)
    assert len(blob) == PACKED_EXTENT
    assert blob == image[PACKED_CONTAINER:PACKED_CONTAINER + PACKED_EXTENT]


def test_the_container_layer_reads_the_initial_width_from_the_kind():
    image = testkit.rom_bytes(ROM, digest=ROM_SHA256)
    unpacked = container.unpack(image, WIDE_CONTAINER, maximum_output=0x40000)
    assert (unpacked.kind, unpacked.declared_size) == (2, WIDE_DECLARED)
    assert len(unpacked.data) == WIDE_DECLARED
    assert jcalg1.decompress(image, WIDE_CONTAINER + 8,
                             WIDE_CONTAINER + unpacked.packed_size) is None


def test_a_truncated_stream_is_refused():
    block = bytes(range(256))
    one = container_at(raw_run([block]), len(block))
    assert jcalg1.decompress(one, 8, len(one)) == (block, len(one) - 8)
    assert jcalg1.decompress(one, 8, 8 + 4) is None
    assert jcalg1.probe(one, 8, 8 + 4)["reason"] == jcalg1.LIMIT


def test_a_stream_whose_end_code_is_past_the_limit_is_refused():
    block = bytes(reversed(range(256)))
    one = container_at(raw_run([block]), len(block))
    consumed = jcalg1.decompress(one, 8, len(one))[1]
    assert jcalg1.probe(one, 8, 8 + consumed)["ok"]
    refusal = jcalg1.probe(one, 8, 8 + consumed - 4)
    assert refusal["ok"] is False
    assert refusal["reason"] == jcalg1.LIMIT


def test_a_raw_run_is_read_in_256_byte_blocks():
    first = bytes(range(256))
    second = bytes(reversed(range(256)))
    one = container_at(raw_run([first]), len(first))
    assert jcalg1.decompress(one, 8, len(one)) == (first, len(one) - 8)
    two = container_at(raw_run([first, second]), len(first) + len(second))
    assert jcalg1.decompress(two, 8, len(two))[0] == first + second


def test_a_back_reference_outside_the_output_is_refused():
    writer = Writer()
    writer.put(0, 1)
    writer.put(1, 1)
    writer.put(1, 1)
    writer.put(0, 1)
    writer.put(1, 8)
    image = container_at(writer.finish(), 256)
    refusal = jcalg1.probe(image, 8, len(image))
    assert refusal["ok"] is False
    assert refusal["reason"] == jcalg1.DISTANCE


def test_the_initial_literal_width_is_the_callers_one_bit():
    writer = Writer()
    writer.put(1, 1)
    writer.put(1, 1)
    writer.put(0, 12)
    image = container_at(writer.finish(), 1)
    assert jcalg1.decompress(image, 8, len(image)) == (b"\x01", len(image) - 8)


def test_an_output_explosion_is_refused_not_allocated():
    for count in (1 << 22, 1 << 24):
        writer = Writer()
        writer.put(1, 1)
        writer.put(0, 1)
        writer.put(0, 1)
        writer.put(1, 1)
        writer.gamma(2)
        writer.gamma(count)
        image = container_at(writer.finish(), 1)
        refusal = jcalg1.probe(image, 8, len(image))
        assert refusal["ok"] is False
        assert refusal["reason"] == jcalg1.OUTPUT
