from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "split"))
sys.path.insert(0, os.path.join(ROOT, "tools", "recomp"))
sys.path.insert(0, HERE)

import code_split
import function_bounds
import name_table

ROM_BASE = code_split.ROM_BASE
THUMB = function_bounds.THUMB
RAM_START = 0x02000000
RAM_END = 0x08000000
STACK = 0x03007F00
RETURN = 0x00000000


class Refused(ValueError):
    pass


def image_bytes(image):
    if isinstance(image, bytearray):
        return bytes(image)
    return image


def half(image, address):
    at = address - ROM_BASE
    return image[at] | (image[at + 1] << 8)


def word(image, address):
    at = address - ROM_BASE
    return int.from_bytes(image[at:at + 4], "little")


class Memory:
    def __init__(self, image, ram=None):
        self.image = image_bytes(image)
        self.ram = dict(ram or {})
        self.writes = []

    def mapped(self, address, size):
        if RAM_START <= address and address + size <= RAM_END:
            return
        if ROM_BASE <= address and address + size <= ROM_BASE + len(self.image):
            return
        raise Refused("0x%08X+%d is outside the image and the writable space"
                      % (address, size))

    def read_byte(self, address):
        self.mapped(address, 1)
        if address - ROM_BASE < len(self.image) and address >= ROM_BASE:
            return self.image[address - ROM_BASE]
        return self.ram.get(address, 0)

    def write_byte(self, address, value, record=True):
        self.mapped(address, 1)
        if address < ROM_BASE:
            if record:
                self.writes.append((address, 1, value & 0xFF))
            self.ram[address] = value & 0xFF
            return
        raise Refused("0x%08X is in the image, which this run may not write" % address)

    def read(self, address, size):
        value = 0
        for offset in range(size):
            value |= self.read_byte(address + offset) << (8 * offset)
        return value

    def write(self, address, size, value):
        self.mapped(address, size)
        for offset in range(size):
            self.write_byte(address + offset, (value >> (8 * offset)) & 0xFF, False)
        self.writes.append((address, size, value & ((1 << (8 * size)) - 1)))

    def half(self, address, value):
        self.write(address, 2, value)

    def word(self, address, value):
        self.write(address, 4, value)

    def blob(self, address, data):
        for offset, byte in enumerate(data):
            self.write(address + offset, 1, byte)


def body_of(image, address):
    starts = name_table.starts() or []
    later = [start for start in starts if start > address]
    limit = later[0] if later else address + 0x400
    return function_bounds.body(image_bytes(image), address, THUMB, limit)


def sign(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def flags_of(result, left, right, subtract, carry, old):
    state = dict(old)
    state["n"] = 1 if result & 0x80000000 else 0
    state["z"] = 1 if result & 0xFFFFFFFF == 0 else 0
    state["c"] = 1 if carry else 0
    top = 0x80000000
    if subtract:
        state["v"] = 1 if ((left ^ right) & (left ^ result) & top) else 0
    else:
        state["v"] = 1 if (~(left ^ right) & (left ^ result) & top) else 0
    return state


def condition(code, flags):
    if code == 0:
        return flags["z"] == 1
    if code == 1:
        return flags["z"] == 0
    if code == 2:
        return flags["c"] == 1
    if code == 3:
        return flags["c"] == 0
    if code == 4:
        return flags["n"] == 1
    if code == 5:
        return flags["n"] == 0
    if code == 6:
        return flags["v"] == 1
    if code == 7:
        return flags["v"] == 0
    if code == 8:
        return flags["c"] == 1 and flags["z"] == 0
    if code == 9:
        return flags["c"] == 0 or flags["z"] == 1
    if code == 10:
        return flags["n"] == flags["v"]
    if code == 11:
        return flags["n"] != flags["v"]
    if code == 12:
        return flags["z"] == 0 and flags["n"] == flags["v"]
    return flags["z"] == 1 or flags["n"] != flags["v"]


def add(registers, flags, destination, left, right, carry_in, subtract, write):
    if subtract:
        unsigned = left - right - carry_in
        result = unsigned & 0xFFFFFFFF
        carry = left >= right + carry_in
        state = flags_of(result, left, right, True, carry, flags)
    else:
        unsigned = left + right + carry_in
        result = unsigned & 0xFFFFFFFF
        state = flags_of(result, left, right, False, unsigned > 0xFFFFFFFF, flags)
    if write:
        if destination == 15:
            return result & ~1, state, True
        registers[destination] = result
    return None, state, False


def shift(kind, value, amount, flags):
    state = dict(flags)
    if amount == 0:
        if kind == 0:
            return value, state
        if kind == 1:
            state["c"] = (value >> 31) & 1
            return 0, state
        state["c"] = (value >> 31) & 1
        return (0xFFFFFFFF if value & 0x80000000 else 0), state
    if kind == 0:
        state["c"] = (value >> (32 - amount)) & 1 if amount <= 32 else 0
        return (value << amount) & 0xFFFFFFFF, state
    if kind == 1:
        state["c"] = (value >> (amount - 1)) & 1 if amount <= 32 else 0
        return (value >> amount) & 0xFFFFFFFF if amount < 32 else 0, state
    signed = value - (1 << 32) if value & 0x80000000 else value
    magnitude = min(amount, 31)
    state["c"] = (signed >> (magnitude - 1)) & 1
    return (signed >> magnitude) & 0xFFFFFFFF, state


def rotate(value, amount):
    amount &= 31
    return ((value >> amount) | (value << (32 - amount))) & 0xFFFFFFFF if amount else value


def execute(image, memory, registers, flags, pc):
    instruction = half(image, pc)
    following = pc + 4
    if instruction < 0x1800:
        kind = instruction >> 11
        amount = (instruction >> 6) & 0x1F
        source = registers[(instruction >> 3) & 7]
        result, state = shift(kind, source, amount, flags)
        registers[instruction & 7] = result
        state = flags_of(result, 0, 0, False, state["c"], state)
        return pc + 2, state, False
    if instruction < 0x2000:
        subtract = (instruction >> 9) & 1
        immediate = (instruction >> 10) & 1
        source = (instruction >> 6) & 7
        right = source if immediate else registers[source]
        target, state, halt = add(registers, flags, instruction & 7,
                                  registers[(instruction >> 3) & 7], right, 0,
                                  subtract, True)
        return target or pc + 2, state, halt
    if instruction < 0x4000:
        kind = (instruction >> 11) & 3
        destination = (instruction >> 8) & 7
        right = instruction & 0xFF
        if kind == 0:
            registers[destination] = right
            return pc + 2, flags, False
        if kind == 1:
            _target, state, _halt = add(registers, flags, 0,
                                        registers[destination], right, 0, True, False)
            return pc + 2, state, False
        target, state, halt = add(registers, flags, destination,
                                  registers[destination], right, 0, kind == 3, True)
        return target or pc + 2, state, halt
    if instruction < 0x4400:
        kind = (instruction >> 6) & 0xF
        source = registers[(instruction >> 3) & 7]
        destination = instruction & 7
        if kind == 0:
            registers[destination] = registers[destination] & source
            state = flags_of(registers[destination], 0, 0, False, flags["c"], flags)
        elif kind == 1:
            registers[destination] = registers[destination] ^ source
            state = flags_of(registers[destination], 0, 0, False, flags["c"], flags)
        elif kind in (2, 3, 4):
            result, state = shift(kind - 2, registers[destination], source & 0xFF, flags)
            registers[destination] = result
            state = flags_of(result, 0, 0, False, state["c"], state)
        elif kind == 5:
            result = registers[destination] + source + flags["c"]
            state = flags_of(result & 0xFFFFFFFF, registers[destination], source, False,
                             result > 0xFFFFFFFF, flags)
            registers[destination] = result & 0xFFFFFFFF
        elif kind == 6:
            result = registers[destination] - source - (1 - flags["c"])
            state = flags_of(result & 0xFFFFFFFF, registers[destination], source, True,
                             registers[destination] >= source + (1 - flags["c"]), flags)
            registers[destination] = result & 0xFFFFFFFF
        elif kind == 7:
            registers[destination] = rotate(registers[destination], source & 0xFF)
            state = flags_of(registers[destination], 0, 0, False,
                             (registers[destination] >> 31) & 1, flags)
        elif kind == 8:
            state = flags_of(registers[destination] & source, 0, 0, False, flags["c"], flags)
        elif kind == 9:
            result = (0 - source) & 0xFFFFFFFF
            state = flags_of(result, 0, source, True, source == 0, flags)
            registers[destination] = result
        elif kind == 10:
            _target, state, _halt = add(registers, flags, 0,
                                        registers[destination], source, 0, True, False)
        elif kind == 11:
            _target, state, _halt = add(registers, flags, 0,
                                        registers[destination], source, 0, False, False)
        elif kind == 12:
            registers[destination] = registers[destination] | source
            state = flags_of(registers[destination], 0, 0, False, flags["c"], flags)
        elif kind == 13:
            registers[destination] = (registers[destination] * source) & 0xFFFFFFFF
            state = flags_of(registers[destination], 0, 0, False,
                             (registers[destination] >> 31) & 1, flags)
        elif kind == 14:
            registers[destination] = registers[destination] & ~source
            state = flags_of(registers[destination], 0, 0, False, flags["c"], flags)
        else:
            registers[destination] = (~source) & 0xFFFFFFFF
            state = flags_of(registers[destination], 0, 0, False, flags["c"], flags)
        return pc + 2, state, False
    if instruction < 0x4800:
        kind = (instruction >> 8) & 3
        destination = (instruction & 7) | (((instruction >> 7) & 1) << 3)
        source = ((instruction >> 3) & 7) | (((instruction >> 6) & 1) << 3)
        if kind == 3:
            return registers[source] & ~1, flags, True
        if kind == 0:
            target, state, halt = add(registers, flags, destination,
                                      registers[destination], registers[source], 0, False,
                                      destination != 15)
            if destination == 15:
                return target, state, True
            return pc + 2, state, halt
        if kind == 1:
            _target, state, _halt = add(registers, flags, 0,
                                        registers[destination], registers[source], 0, True,
                                        False)
            return pc + 2, state, False
        registers[destination] = registers[source]
        return pc + 2, flags, False
    if instruction < 0x5000:
        destination = (instruction >> 8) & 7
        registers[destination] = memory.read(((following & ~3) + (instruction & 0xFF) * 4), 4)
        return pc + 2, flags, False
    if instruction < 0x6000:
        kind = (instruction >> 9) & 7
        offset = registers[(instruction >> 6) & 7]
        address = registers[(instruction >> 3) & 7] + offset
        destination = instruction & 7
        if kind == 4:
            registers[destination] = memory.read(address, 4)
        elif kind == 5:
            registers[destination] = memory.read(address, 2)
        elif kind == 6:
            registers[destination] = memory.read(address, 1)
        elif kind == 7:
            registers[destination] = sign(memory.read(address, 2), 16) & 0xFFFFFFFF
        elif kind == 3:
            registers[destination] = sign(memory.read(address, 1), 8) & 0xFFFFFFFF
        else:
            size = 4 if kind == 0 else (2 if kind == 1 else 1)
            memory.write(address, size, registers[destination])
        return pc + 2, flags, False
    if instruction < 0x8000:
        kind = (instruction >> 11) & 3
        offset = (instruction >> 6) & 0x1F
        address = registers[(instruction >> 3) & 7]
        destination = instruction & 7
        if kind == 0:
            memory.write(address + offset * 4, 4, registers[destination])
        elif kind == 1:
            registers[destination] = memory.read(address + offset * 4, 4)
        elif kind == 2:
            memory.write(address + offset, 1, registers[destination])
        else:
            registers[destination] = memory.read(address + offset, 1)
        return pc + 2, flags, False
    if instruction < 0x9000:
        load = (instruction >> 11) & 1
        offset = ((instruction >> 6) & 0x1F) * 2
        address = registers[(instruction >> 3) & 7] + offset
        destination = instruction & 7
        if load:
            registers[destination] = memory.read(address, 2)
        else:
            memory.write(address, 2, registers[destination])
        return pc + 2, flags, False
    if instruction < 0xA000:
        load = (instruction >> 11) & 1
        address = registers[13] + (instruction & 0xFF) * 4
        destination = (instruction >> 8) & 7
        if load:
            registers[destination] = memory.read(address, 4)
        else:
            memory.write(address, 4, registers[destination])
        return pc + 2, flags, False
    if instruction < 0xB000:
        base = (following & ~3) if ((instruction >> 11) & 1) == 0 else registers[13]
        registers[(instruction >> 8) & 7] = base + (instruction & 0xFF) * 4
        return pc + 2, flags, False
    if (instruction & 0xFF00) == 0xB000:
        amount = (instruction & 0x7F) * 4
        registers[13] = ((registers[13] - amount) if instruction & 0x80
                         else (registers[13] + amount)) & 0xFFFFFFFF
        return pc + 2, flags, False
    if (instruction & 0xFE00) == 0xB400:
        listed = [number for number in range(8) if instruction & (1 << number)]
        if instruction & 0x100:
            listed.append(14)
        registers[13] = (registers[13] - 4 * len(listed)) & 0xFFFFFFFF
        for index, number in enumerate(listed):
            memory.write(registers[13] + 4 * index, 4, registers[number])
        return pc + 2, flags, False
    if (instruction & 0xFE00) == 0xBC00:
        listed = [number for number in range(8) if instruction & (1 << number)]
        returning = bool(instruction & 0x100)
        for index, number in enumerate(listed):
            registers[number] = memory.read(registers[13] + 4 * index, 4)
        registers[13] = (registers[13] + 4 * (len(listed) + (1 if returning else 0))) \
            & 0xFFFFFFFF
        if returning:
            return memory.read(registers[13] - 4, 4) & ~1, flags, True
        return pc + 2, flags, False
    if instruction < 0xD000:
        load = (instruction >> 11) & 1
        listed = [number for number in range(8) if instruction & (1 << number)]
        base = (instruction >> 8) & 7
        address = registers[base]
        if load:
            for index, number in enumerate(listed):
                registers[number] = memory.read(address + 4 * index, 4)
        else:
            for index, number in enumerate(listed):
                memory.write(address + 4 * index, 4, registers[number])
        if not (load and base in listed):
            registers[base] = address + 4 * len(listed)
        return pc + 2, flags, False
    if instruction < 0xDF00:
        if condition((instruction >> 8) & 0xF, flags):
            return pc + 4 + 2 * sign(instruction & 0xFF, 8), flags, False
        return pc + 2, flags, False
    if instruction < 0xE000:
        raise Refused("0x%08X is a BIOS call, which this run cannot make" % pc)
    if instruction < 0xE800:
        return pc + 4 + 2 * sign(instruction & 0x7FF, 11), flags, False
    if instruction >= 0xF000:
        low = half(image, pc + 2)
        offset = ((instruction & 0x7FF) << 12) | ((low & 0x7FF) << 1)
        return None, flags, sign(offset, 23)

    raise Refused("0x%08X holds 0x%04X, which is not a Thumb instruction" % (pc, instruction))


def run(image, address, registers=None, memory=None, body=None, budget=0x1000, stubs=None):
    image = image_bytes(image)
    if body is None:
        body = body_of(image, address)
    body = set(body)
    if memory is None:
        memory = Memory(image)
    state = [0] * 16
    state[13] = STACK
    state[14] = RETURN
    for number, value in dict(registers or {}).items():
        state[number] = value & 0xFFFFFFFF
    flags = {"n": 0, "z": 0, "c": 0, "v": 0}
    stubs = dict(stubs or {})
    calls = []
    pc = address
    steps = 0
    while True:
        if steps >= budget:
            raise Refused("the run passed the step budget of %d at 0x%08X" % (budget, pc))
        steps += 1
        following = pc + 4
        target, flags, halt = execute(image, memory, state, flags, pc)
        if target is None:
            call = sign(((half(image, pc) & 0x7FF) << 12) | ((half(image, pc + 2) & 0x7FF) << 1),
                        23) + following
            calls.append((pc, call))
            state[14] = (pc + 2) | 1
            if call in stubs:
                for number, value in stubs[call].items():
                    state[number] = value & 0xFFFFFFFF
            pc = pc + 4
            continue
        if halt:
            state[15] = target & 0xFFFFFFFF
            return {"registers": state, "written": memory.writes, "calls": calls,
                    "steps": steps, "returned": target & ~1}
        if target not in body:
            raise Refused("the run left the body at 0x%08X from 0x%08X" % (target, pc))
        pc = target
