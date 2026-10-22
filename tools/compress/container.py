from __future__ import annotations

from dataclasses import dataclass
import struct

STORED = 0
PACKED_KINDS = (1, 2)

HEADER_SIZE = 8

DEFAULT_MAX_OUTPUT = 64 * 1024

_MARKER_SCAN_SLACK = 4 * 1024


def _gamma_ceiling(maximum_output: int) -> int:
    return maximum_output + 3


class ContainerError(ValueError):
    pass


@dataclass(frozen=True)
class Container:

    offset: int
    kind: int
    declared_size: int
    packed_end: int
    data: bytes

    @property
    def packed_size(self) -> int:
        return self.packed_end - self.offset


class _WordBitReader:

    __slots__ = ("_data", "_position", "_word", "_remaining")

    def __init__(self, data: bytes, offset: int) -> None:
        self._data = data
        self._position = offset
        self._word = 0
        self._remaining = 0

    def bit(self) -> int:
        if self._remaining == 0:
            if self._position + 4 > len(self._data):
                raise ContainerError("packed stream ended inside a bit word")
            self._word = struct.unpack_from("<I", self._data, self._position)[0]
            self._position += 4
            self._remaining = 32
        result = (self._word >> 31) & 1
        self._word = (self._word << 1) & 0xFFFFFFFF
        self._remaining -= 1
        return result

    def get(self, count: int) -> int:
        value = 0
        for _ in range(count):
            value = (value << 1) | self.bit()
        return value

    @property
    def position(self) -> int:
        return self._position


def _gamma(reader: _WordBitReader, minimum: int) -> int:
    value = 1
    while True:
        value = (value << 1) | reader.bit()
        if value >= minimum:
            raise ContainerError(
                f"gamma value reached {value}, over the {minimum} ceiling its own "
                "field can carry"
            )
        if reader.bit() == 0:
            return value


def _input_scan_limit(expected: int) -> int:
    return expected + expected // 4 + _MARKER_SCAN_SLACK


def _emit_raw(out: bytearray, value: int, expected: int) -> None:
    if len(out) >= expected:
        raise ContainerError(
            f"raw literal run at output offset {len(out)} overruns the declared "
            f"{expected}"
        )
    out.append(value)


def _unpack_stream(
    data: bytes,
    payload: int,
    expected: int,
    initial_literal_bits: int,
    *,
    require_end_marker: bool = False,
    maximum_output: int = DEFAULT_MAX_OUTPUT,
) -> tuple[bytes, int]:
    reader = _WordBitReader(data, payload)
    out = bytearray()
    literal_base = 0
    literal_bits = initial_literal_bits
    distance_bits = 8
    previous_distance = 1
    scan_limit = _input_scan_limit(expected)
    gamma_ceiling = _gamma_ceiling(maximum_output)

    def copy_match(distance: int, count: int) -> None:
        if distance == 0 or distance > len(out):
            raise ContainerError(
                f"back-reference distance {distance} at output offset {len(out)} "
                "points outside the decoded output"
            )
        if len(out) + count > expected:
            raise ContainerError(
                f"match at output offset {len(out)} would produce "
                f"{len(out) + count} bytes against a declared {expected}"
            )
        for _ in range(count):
            out.append(out[-distance])

    while len(out) < expected or require_end_marker:
        if reader.position - payload > scan_limit:
            raise ContainerError(
                f"packed stream consumed over {scan_limit} input bytes for a "
                f"declared {expected} without finishing"
            )
        if reader.bit():
            if len(out) >= expected:
                raise ContainerError(
                    f"literal at output offset {len(out)} overruns the declared "
                    f"{expected}"
                )
            out.append((literal_base + reader.get(literal_bits)) & 0xFF)
            continue

        if reader.bit():
            distance_code = _gamma(reader, gamma_ceiling)
            if distance_code == 2:
                copy_match(previous_distance, _gamma(reader, gamma_ceiling))
                continue
            distance = reader.get(distance_bits) + ((distance_code - 3) << distance_bits)
            previous_distance = distance
            count = _gamma(reader, gamma_ceiling)
            if distance >= 0x10000:
                count += 3
            elif distance >= 0x37FF:
                count += 2
            elif distance >= 0x027F:
                count += 1
            elif distance <= 0x007F:
                count += 4
            copy_match(distance, count)
            continue

        if reader.bit() == 0:
            distance = reader.get(7)
            if distance != 0:
                previous_distance = distance
                copy_match(distance, reader.get(2) + 2)
                continue
            width = reader.get(2)
            if width == 0:
                break
            distance_bits = reader.get(width + 3)
            continue

        short_distance = reader.get(4) - 1
        if short_distance == 0:
            if len(out) >= expected:
                raise ContainerError(
                    f"base-literal at output offset {len(out)} overruns the "
                    f"declared {expected}"
                )
            out.append(literal_base & 0xFF)
        elif short_distance > 0:
            copy_match(short_distance, 1)
        elif reader.bit():
            while True:
                _emit_raw(out, reader.get(8), expected)
                _emit_raw(out, reader.get(8), expected)
                if reader.bit() == 0:
                    break
        else:
            literal_bits = 7 + reader.bit()
            if literal_bits == 8:
                literal_base = 0
            else:
                literal_base = reader.get(8)

    if len(out) != expected:
        raise ContainerError(
            f"packed stream decoded {len(out)} bytes against a declared {expected}"
        )
    return bytes(out), reader.position


def read_header(data: bytes, offset: int) -> tuple[int, int]:
    if offset < 0 or offset + HEADER_SIZE > len(data):
        raise ContainerError(f"container header at {offset:#x} is outside the image")
    kind, declared = struct.unpack_from("<II", data, offset)
    return kind, declared


def looks_like_container(
    data: bytes,
    offset: int,
    *,
    minimum_size: int = 1,
    maximum_size: int = DEFAULT_MAX_OUTPUT,
) -> bool:
    if offset < 0 or offset + HEADER_SIZE > len(data):
        return False
    kind, declared = struct.unpack_from("<II", data, offset)
    return kind <= 2 and minimum_size <= declared <= maximum_size


def unpack(
    data: bytes,
    offset: int,
    *,
    maximum_output: int = DEFAULT_MAX_OUTPUT,
    require_end_marker: bool = False,
) -> Container:
    kind, declared = read_header(data, offset)
    if declared > maximum_output:
        raise ContainerError(
            f"container at {offset:#x} declares {declared} bytes, over the "
            f"{maximum_output}-byte safety limit"
        )

    payload = offset + HEADER_SIZE
    if kind == STORED:
        if payload + declared > len(data):
            raise ContainerError(f"stored container at {offset:#x} runs past the image")
        return Container(
            offset=offset,
            kind=kind,
            declared_size=declared,
            packed_end=payload + declared,
            data=data[payload : payload + declared],
        )
    if kind in PACKED_KINDS:
        decoded, end = _unpack_stream(
            data,
            payload,
            declared,
            kind,
            require_end_marker=require_end_marker,
            maximum_output=maximum_output,
        )
        return Container(
            offset=offset,
            kind=kind,
            declared_size=declared,
            packed_end=end,
            data=decoded,
        )
    raise ContainerError(f"unsupported Webfoot container kind {kind} at {offset:#x}")
