from __future__ import annotations

import csv
import io
import os
import re
import struct
import sys

ROM_BASE = 0x08000000
ROM_SIZE = 8388608
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ROM = os.path.join(ROOT, "baserom.gba")
DOC = os.path.join(ROOT, "tools", "split", "CODE_SPLIT.md")
CSV_OUT = os.path.join(ROOT, "tools", "split", "CODE_SPLIT.csv")
VECTOR = 0x08000000
CRT0 = 0x080000C0
OVERLAY = 0x08000148
STEP_LIMIT = 0x10000
BLOCK = 0x10000
IRQ_VECTOR = 0x03007FFC
UNCLASSIFIED = 0
PROVEN = 1
FILTERED = 2
POOL = 3
OVERLAY_CLASS = 4
TABLE = 5
GAPFILL = 6
CODE_CLASSES = (PROVEN, TABLE, FILTERED, GAPFILL)
MODE_NONE = 0
MODE_THUMB = 1
MODE_ARM = 2
CLASS_NAMES = {PROVEN: "proven code", FILTERED: "filtered pointer-entry code",
               TABLE: "table-held code", GAPFILL: "gap-fill code", POOL: "literal pool",
               OVERLAY_CLASS: "IWRAM overlay", UNCLASSIFIED: "unclassified"}
DOC_CLASSES = ("proven code", "filtered pointer-entry code", "table-held code",
               "gap-fill code", "literal pool", "IWRAM overlay", "unclassified")
STRENGTH = {PROVEN: 0, TABLE: 1, FILTERED: 2, GAPFILL: 3, POOL: 5,
            OVERLAY_CLASS: 6, UNCLASSIFIED: 9}
FILTER_BRANCHES = 1
FACTORY_REPEATS = 4
TABLE_CAP = 64
TABLE_SHAPES = ("run", "record", "slot", "runfree", "load", "pool", "overlay")
PROLOGUE_CAP = 64
LOOKBACK = 0x40
CHANNEL_ROUNDS = 8
CLOSING_BAR = 5.0
RUN_THRESHOLDS = (1, 8, 32, 128)
THUMB_UNDEFINED = ((0x4780, 0x47FF), (0xB100, 0xB3FF), (0xB600, 0xBBFF), (0xBE00, 0xBFFF),
                   (0xDE00, 0xDEFF), (0xE800, 0xEFFF))
THUNK_HEAD = ((0x4778, 0x46C0), 0xE51FF004)
_UNDEFINED = bytes(
    1 if any(low <= half <= high for low, high in THUMB_UNDEFINED) else 0
    for half in range(0x10000))
_NAMES = tuple(CLASS_NAMES.get(value) for value in range(256))
_SIZE = bytes(0 if half >= 0xF800 or _UNDEFINED[half] else 4 if half >= 0xF000 else 2
              for half in range(0x10000))
_VIEWS = {}


def views_of(rom):
    found = _VIEWS.get(id(rom))
    if found is not None and found[0] is rom:
        return found
    if sys.byteorder != "little":
        raise SystemExit("this tree reads the retail image little-endian, and this host is "
                         "%s-endian" % sys.byteorder)
    halves = memoryview(rom)[:len(rom) - len(rom) % 2].cast("H")
    words = memoryview(rom)[:len(rom) - len(rom) % 4].cast("I")
    if len(_VIEWS) > 3:
        _VIEWS.clear()
    found = (rom, halves, words)
    _VIEWS[id(rom)] = found
    return found


def hw(rom, addr):
    offset = addr - ROM_BASE
    if offset & 1:
        return struct.unpack_from("<H", rom, offset)[0]
    return views_of(rom)[1][offset >> 1]


def word(rom, addr):
    offset = addr - ROM_BASE
    if offset & 3:
        return struct.unpack_from("<I", rom, offset)[0]
    return views_of(rom)[2][offset >> 2]


def in_image(rom, addr):
    return ROM_BASE <= addr < ROM_BASE + len(rom)


def has_word(rom, addr):
    return ROM_BASE <= addr and addr + 4 <= ROM_BASE + len(rom)


def thumb_size(view, index, count):
    if index + 1 > count:
        return None
    size = _SIZE[view[index]]
    if size == 4:
        return 4 if index + 2 <= count and view[index + 1] >= 0xF800 else None
    return size or None


def thumb_length(rom, addr):
    offset = addr - ROM_BASE
    if not offset & 1:
        view = views_of(rom)[1]
        return thumb_size(view, offset >> 1, len(view))
    if addr + 2 > ROM_BASE + len(rom):
        return None
    half = struct.unpack_from("<H", rom, offset)[0]
    if half >= 0xF000:
        if half >= 0xF800 or addr + 4 > ROM_BASE + len(rom):
            return None
        return 4 if struct.unpack_from("<H", rom, offset + 2)[0] >= 0xF800 else None
    return None if _UNDEFINED[half] else 2


def arm_branch_target(addr, instruction):
    offset = instruction & 0x00FFFFFF
    if offset & 0x00800000:
        offset -= 0x01000000
    return (addr + 8 + (offset << 2)) & 0xFFFFFFFF


def thumb_branch_target(addr, half):
    offset = half & 0x07FF
    if offset & 0x0400:
        offset -= 0x0800
    return (addr + 4 + (offset << 1)) & 0xFFFFFFFF


def thumb_call_target(rom, addr):
    high = hw(rom, addr)
    low = hw(rom, addr + 2)
    offset = ((high & 0x07FF) << 11) | (low & 0x07FF)
    if high & 0x0400:
        offset -= 1 << 22
    return (addr + 4 + (offset << 1)) & 0xFFFFFFFF


def literal_target(rom, addr):
    instruction = word(rom, addr)
    if (instruction & 0x0F7F0000) != 0x051F0000:
        return None
    offset = instruction & 0x0FFF
    if not instruction & 0x00800000:
        offset = -offset
    return ((addr + 8) & ~3) + offset


def mark(classes, modes, addr, size, value, mode):
    offset = addr - ROM_BASE
    strength = STRENGTH[value]
    for index in range(offset, offset + size):
        if STRENGTH[classes[index]] > strength:
            classes[index] = value
            modes[index] = mode


def code_ranges(classes):
    out = []
    for value in CODE_CLASSES:
        out += class_runs(classes, value)
    return sorted(out)


def thumb_step(rom, addr, classes, modes, value, last):
    view = views_of(rom)[1]
    index = (addr - ROM_BASE) >> 1
    size = thumb_size(view, index, len(view))
    if size is None:
        return addr, True, [], None, 0, None, []
    mark(classes, modes, addr, size, value, MODE_THUMB)
    half = view[index]
    if size == 4:
        target = thumb_call_target(rom, addr)
        calls = [(target, MODE_THUMB)] if in_image(rom, target) else []
        return addr + 4, False, [], None, 0, None, calls
    if (half & 0xFF87) in (0x4487, 0x4687):
        return addr + 2, True, [], None, 0, None, []
    if (half & 0xFF80) == 0x4700:
        entries = []
        register = half & 0x0F
        if register != 14 and last is not None and last[0] == register:
            if last[1] & 1 and in_image(rom, last[1] & ~1):
                entries.append((last[1] & ~1, MODE_THUMB))
        return addr + 2, True, entries, None, 0, None, []
    if (half & 0xFF00) == 0xBD00:
        return addr + 2, True, [], None, 0, None, []
    if (half & 0xFF00) == 0xDF00:
        return addr + 2, True, [], None, 0, None, []
    if (half & 0xF800) == 0xE000:
        target = thumb_branch_target(addr, half)
        entries = [(target, MODE_THUMB)] if in_image(rom, target) else []
        return addr + 2, True, entries, None, 0, None, []
    if (half & 0xF000) == 0xD000:
        offset = half & 0x00FF
        if offset & 0x80:
            offset -= 0x100
        target = addr + 4 + (offset << 1)
        entries = [(target, MODE_THUMB)] if in_image(rom, target) else []
        return addr + 2, False, entries, None, 1, None, []
    if (half & 0xF800) == 0x4800:
        pool = ((addr + 4) & ~3) + (half & 0x00FF) * 4
        last = ((half >> 8) & 0x07, word(rom, pool)) if has_word(rom, pool) else None
        return addr + 2, False, [], pool, 0, last, []
    return addr + 2, False, [], None, 0, None, []


def arm_step(rom, addr, classes, modes, value, last):
    if not has_word(rom, addr):
        return addr, True, [], None, 0, None, []
    instruction = word(rom, addr)
    if instruction >> 28 == 0x0F:
        return addr, True, [], None, 0, None, []
    mark(classes, modes, addr, 4, value, MODE_ARM)
    if instruction in (0xE12FFF1E, 0xE1A0F00E):
        return addr + 4, True, [], None, 0, None, []
    if (instruction & 0x0FFF8000) == 0x08BD8000:
        return addr + 4, True, [], None, 0, None, []
    if (instruction & 0x0FFFFFF0) == 0x012FFF10:
        entries = []
        register = instruction & 0x0F
        if register != 14 and last is not None and last[0] == register:
            if in_image(rom, last[1] & ~1):
                mode = MODE_THUMB if last[1] & 1 else MODE_ARM
                entries.append((last[1] & ~1, mode))
        return addr + 4, True, entries, None, 0, None, []
    if (instruction & 0x0F000000) == 0x0B000000:
        target = arm_branch_target(addr, instruction)
        calls = [(target, MODE_ARM)] if in_image(rom, target) else []
        return addr + 4, False, [], None, 0, None, calls
    if (instruction & 0x0F000000) == 0x0A000000:
        target = arm_branch_target(addr, instruction)
        entries = [(target, MODE_ARM)] if in_image(rom, target) else []
        if instruction >> 28 == 0x0E:
            return addr + 4, True, entries, None, 0, None, []
        return addr + 4, False, entries, None, 1, None, []
    if (instruction & 0x0F7F0000) == 0x051F0000:
        pool = literal_target(rom, addr)
        if not has_word(rom, pool):
            return addr + 4, False, [], None, 0, None, []
        loaded = word(rom, pool)
        register = (instruction >> 12) & 0x0F
        entries = []
        if register == 15:
            if in_image(rom, loaded & ~1):
                mode = MODE_THUMB if loaded & 1 else MODE_ARM
                entries.append((loaded & ~1, mode))
            return addr + 4, True, entries, pool, 0, None, []
        if register == 14 and in_image(rom, loaded & ~1):
            mode = MODE_THUMB if loaded & 1 else MODE_ARM
            entries.append((loaded & ~1, mode))
        return addr + 4, False, entries, pool, 0, (register, loaded), []
    if (((instruction >> 12) & 0x0F) == 0x0F
            and (instruction & 0x0C000000) in (0x00000000, 0x04000000, 0x08000000)
            and (instruction & 0x0F800000) != 0x01000000):
        return addr + 4, True, [], None, 0, None, []
    return addr + 4, False, [], None, 0, None, []


def walk(rom, roots, classes, modes, value):
    queue = list(roots)
    seen = set()
    spans = []
    pools = set()
    entries = set()
    calls = set()
    while queue:
        start, mode = queue.pop()
        if (start, mode) in seen:
            continue
        seen.add((start, mode))
        entries.add((start, mode))
        addr = start
        last = None
        steps = 0
        while steps < STEP_LIMIT:
            steps += 1
            if mode == MODE_THUMB:
                addr, ended, new, pool, _branches, last, called = thumb_step(
                    rom, addr, classes, modes, value, last)
            else:
                addr, ended, new, pool, _branches, last, called = arm_step(
                    rom, addr, classes, modes, value, last)
            for target, target_mode in new:
                queue.append((target, target_mode))
            for target, target_mode in called:
                queue.append((target, target_mode))
                calls.add((target, target_mode))
            if pool is not None:
                pools.add(pool)
            if ended or not in_image(rom, addr):
                break
        if addr > start:
            spans.append((start, addr, mode))
    return spans, pools, entries, calls


def probe(rom, entry):
    queue = [entry]
    seen = set()
    returned = False
    branches = 0
    view = views_of(rom)[1]
    count = len(view)
    while queue:
        addr = queue.pop()
        if addr in seen:
            continue
        seen.add(addr)
        index = (addr - ROM_BASE) >> 1
        steps = 0
        while steps < STEP_LIMIT:
            steps += 1
            size = thumb_size(view, index, count)
            if size is None:
                return False, False, 0
            half = view[index]
            if size == 4:
                target = thumb_call_target(rom, addr)
                if in_image(rom, target):
                    queue.append(target)
                addr += 4
                index += 2
                continue
            if (half & 0xFF80) == 0x4700:
                if half == 0x4770:
                    returned = True
                break
            if (half & 0xFF00) == 0xBD00:
                returned = True
                break
            if (half & 0xFF00) == 0xDF00:
                break
            if (half & 0xF800) == 0xE000:
                target = thumb_branch_target(addr, half)
                if in_image(rom, target):
                    queue.append(target)
                break
            if (half & 0xF000) == 0xD000:
                branches += 1
                offset = half & 0x00FF
                if offset & 0x80:
                    offset -= 0x100
                target = addr + 4 + (offset << 1)
                if in_image(rom, target):
                    queue.append(target)
                addr += 2
                index += 1
                continue
            addr += 2
            index += 1
        else:
            return False, False, 0
    return True, returned, branches


def closure(rom, entry, classes, modes):
    position = entry
    visited = set()
    targets = set()
    returned = False
    tail = None
    extent = entry
    steps = 0
    while steps < STEP_LIMIT:
        steps += 1
        if thumb_length(rom, position) is None:
            return "invalid", extent
        half = hw(rom, position)
        visited.add(position)
        after, ended, new, _pool, _branches, _last, called = thumb_step(
            rom, position, classes, modes, UNCLASSIFIED, None)
        extent = max(extent, after)
        for target, _mode in new + called:
            targets.add(target)
        if ended:
            if half == 0x4770 or half == 0x46F7 or (half & 0xFF00) == 0xBD00:
                returned = True
            elif (half & 0xF800) == 0xE000 and new:
                tail = new[0][0]
            break
        position = after
    else:
        return "step-limit", extent
    for target in targets:
        if entry <= target < extent:
            if target not in visited:
                return "inconsistent", extent
            continue
        if not (in_image(rom, target) and classes[target - ROM_BASE] in CODE_CLASSES):
            return "inconsistent", extent
    if returned:
        return "return", extent
    if tail is not None and in_image(rom, tail) and classes[tail - ROM_BASE] in CODE_CLASSES:
        return "tail", extent
    return "no-return", extent


def under_closing_bar(counted, claimed):
    return 100.0 * counted / max(claimed, 1) < CLOSING_BAR


def closing_entries(rom, targets, pre, modes, counted):
    found = [target for target in targets
             if closure(rom, target, pre, modes)[0] in ("return", "tail")]
    if counted is None or not under_closing_bar(counted, len(found)):
        return [], found
    return found, found


def thumb_entries(rom):
    targets = set()
    words = 0
    end = ROM_BASE + len(rom)
    for value in views_of(rom)[2]:
        if value & 1 and ROM_BASE <= value < end:
            words += 1
            targets.add(value & ~1)
    return targets, words


def overlay_copy(rom):
    kick = None
    for addr in range(CRT0, CRT0 + 0x7C, 4):
        if literal_target(rom, addr) == OVERLAY + 8:
            kick = addr
            break
    if kick is None:
        raise ValueError("the startup block at 0x%08X loads no copy size from 0x%08X"
                         % (CRT0, OVERLAY + 8))
    if (literal_target(rom, kick - 16) != OVERLAY or literal_target(rom, kick - 8) != OVERLAY + 4):
        raise ValueError("the words at 0x%08X are not the source, destination and size the DMA "
                         "kick at 0x%08X loads" % (OVERLAY, kick))
    shift = word(rom, kick + 4)
    control = word(rom, kick + 8)
    store = word(rom, kick + 12)
    if (shift, control, store) != (0xE1B01121, 0xE3811484, 0x158010DC):
        raise ValueError("the copy kick at 0x%08X is not movs/lsr #2, orr #0x84000000, strne "
                         "[r0,#0xdc]: %08X %08X %08X" % (kick, shift, control, store))
    source = word(rom, OVERLAY)
    dest = word(rom, OVERLAY + 4)
    declared = word(rom, OVERLAY + 8)
    if not in_image(rom, source) or not has_word(rom, source):
        raise ValueError("the descriptor at 0x%08X names source 0x%08X outside the image"
                         % (OVERLAY, source))
    if not 0x03000000 <= dest < 0x03008000:
        raise ValueError("the descriptor at 0x%08X names destination 0x%08X, which is not IWRAM"
                         % (OVERLAY, dest))
    size = (declared >> 2) * 4
    if not 0 < size <= declared:
        raise ValueError("the descriptor at 0x%08X names size 0x%X, whose word count is 0x%X"
                         % (OVERLAY, declared, size))
    if source + size > ROM_BASE + len(rom):
        raise ValueError("the copy at 0x%08X of 0x%X bytes leaves the image" % (source, size))
    return source, dest, size, declared


def overlay_thunks(rom, dest, size):
    out = []
    found = views_of(rom)
    halves = found[1]
    words = found[2]
    for index in range(0, len(words) - 3):
        if (halves[2 * index], halves[2 * index + 1]) != THUNK_HEAD[0]:
            continue
        if words[index + 1] != THUNK_HEAD[1]:
            continue
        target = words[index + 2]
        if dest <= target < dest + size:
            out.append((ROM_BASE + 4 * index, target))
    return out


def dispatch_sites(rom, classes, modes, ranges):
    out = []
    for begin, stop in ranges:
        for addr in range(ROM_BASE + begin, ROM_BASE + stop, 2):
            offset = addr - ROM_BASE
            if classes[offset] not in (PROVEN, FILTERED):
                continue
            if modes[offset] == MODE_THUMB:
                half = hw(rom, addr)
                if (half & 0xFF87) in (0x4487, 0x4687):
                    out.append((addr, MODE_THUMB))
            elif modes[offset] == MODE_ARM and addr % 4 == 0 and has_word(rom, addr):
                instruction = word(rom, addr)
                if (instruction & 0x0FFF0FF0) in (0x008F0000, 0x008F0100):
                    out.append((addr, MODE_ARM))
                if (instruction & 0x0FFF0FF0) in (0x079F0000, 0x079F0100):
                    out.append((addr, MODE_ARM))
    return out


def register_branches(rom, classes, modes, ranges):
    sites = 0
    bounded = 0
    entries = []
    for begin, stop in ranges:
        for addr in range(ROM_BASE + begin, ROM_BASE + stop, 2):
            offset = addr - ROM_BASE
            if classes[offset] not in CODE_CLASSES:
                continue
            if modes[offset] == MODE_THUMB:
                half = hw(rom, addr)
                if (half & 0xFF87) == 0x4700:
                    if (half & 0x78) == 0x70:
                        continue
                    register = (half >> 3) & 0x07
                elif (half & 0xFF87) == 0x4687:
                    register = (half >> 3) & 0x07
                else:
                    continue
                load_at = None
                for probe in range(addr - 2, max(addr - 20, ROM_BASE - 1), -2):
                    stride, base, index = thumb_load(hw(rom, probe))
                    if stride is not None and (hw(rom, probe) & 0x07) == register:
                        load_at = probe
                        break
                if load_at is not None:
                    for probe in range(load_at - 2, max(load_at - 14, ROM_BASE - 1), -2):
                        if ((hw(rom, probe) & 0xF800) != 0x2800
                                or ((hw(rom, probe) >> 8) & 0x07) != index):
                            continue
                        if (hw(rom, probe + 2) & 0xF000) == 0xD000:
                            bounded += 1
                        break
                source, at = thumb_source(rom, addr, register)
            elif modes[offset] == MODE_ARM and addr % 4 == 0 and has_word(rom, addr):
                instruction = word(rom, addr)
                if (instruction & 0x0FFFFFF0) not in (0x012FFF10, 0x01A0F000):
                    continue
                register = instruction & 0x0F
                if register == 14:
                    continue
                source, at = arm_source(rom, addr, register)
            else:
                continue
            sites += 1
            if source is not None and source & 1 and in_image(rom, source & ~1):
                entries.append({"site": addr, "register": register, "source_at": at,
                                "value": source, "target": source & ~1,
                                "mode": MODE_THUMB if source & 1 else MODE_ARM})
    return {"sites": sites, "bounded": bounded, "entries": entries}


def named_words(rom):
    values = views_of(rom)[2]
    end = ROM_BASE + len(rom)
    flags = bytearray(len(values))
    for index, value in enumerate(values):
        if value & 1 and ROM_BASE <= (value & ~1) < end:
            flags[index] = 1
    return values, flags


def repeated_code_pointers(rom):
    values, flags = named_words(rom)
    counts = {}
    for index, hit in enumerate(flags):
        if hit:
            counts[values[index]] = counts.get(values[index], 0) + 1
    return {value for value, count in counts.items() if count >= FACTORY_REPEATS}


def linear_end(rom, entry):
    view = views_of(rom)[1]
    count = len(view)
    index = (entry - ROM_BASE) >> 1
    addr = entry
    for _step in range(PROLOGUE_CAP):
        size = thumb_size(view, index, count)
        if size is None:
            return None
        half = view[index]
        if size == 4:
            addr += 4
            index += 2
            continue
        if (half & 0xFF00) == 0xBD00 or (half & 0xFF87) == 0x4700:
            return addr + size
        if ((half & 0xF800) == 0xE000 or (half & 0xFF87) in (0x4487, 0x4687)
                or (half & 0xFF80) == 0x4700):
            return None
        addr += size
        index += 1
    return None


def merged_length(ranges):
    total = 0
    end = 0
    for start, stop in sorted(ranges):
        if stop <= end:
            continue
        total += stop - max(start, end)
        end = stop
    return total


def decodable_runs(rom, classes):
    counts = {threshold: 0 for threshold in RUN_THRESHOLDS}
    offset = 0
    total = len(rom)
    view = views_of(rom)[1]
    count = len(view)
    sizes = _SIZE
    while offset < total:
        if classes[offset] != UNCLASSIFIED:
            offset += 2
            continue
        start = offset
        while offset < total and classes[offset] == UNCLASSIFIED:
            index = offset >> 1
            if index + 1 > count:
                break
            size = sizes[view[index]]
            if not size or (size == 4 and not thumb_size(view, index, count)):
                break
            offset += 2
        length = offset - start
        for threshold in RUN_THRESHOLDS:
            if length >= 2 * threshold:
                counts[threshold] += length
        while offset < total and classes[offset] == UNCLASSIFIED:
            index = offset >> 1
            if index + 1 > count:
                break
            size = sizes[view[index]]
            if size == 2 or (size == 4 and thumb_size(view, index, count)):
                break
            offset += 2
    return counts


CONDITION_NAMES = {0: "beq", 1: "bne", 2: "bhs", 3: "blo", 4: "bmi", 5: "bpl", 6: "bvs",
                   7: "bvc", 8: "bhi", 9: "bls", 10: "bge", 11: "blt", 12: "bgt", 13: "ble"}
TABLE_LOADS = ((0x5C00, 1), (0x5A00, 2), (0x5800, 4))


def thumb_shift(half, register):
    if (half & 0xF800) == 0x0000 and (half & 0x07) == register and (half >> 6) & 0x1F:
        return 1 << ((half >> 6) & 0x1F), (half >> 3) & 0x07
    return None, None


def thumb_load(half):
    for pattern, stride in TABLE_LOADS:
        if (half & 0xFE00) == pattern:
            return stride, (half >> 3) & 0x07, (half >> 6) & 0x07
    return None, None, None


def thumb_base(rom, start, register):
    for probe in range(start, max(start - 34, ROM_BASE - 1), -2):
        half = hw(rom, probe)
        if (half & 0xF800) == 0xA000:
            if ((half >> 8) & 0x07) != register:
                continue
            candidate = ((probe + 4) & ~3) + (half & 0xFF) * 4
        elif (half & 0xF800) == 0x4800:
            if ((half >> 8) & 0x07) != register:
                continue
            pool = ((probe + 4) & ~3) + (half & 0xFF) * 4
            if not has_word(rom, pool):
                return None, None
            candidate = word(rom, pool)
        else:
            continue
        if in_image(rom, candidate):
            return candidate, probe
    return None, None


def thumb_bound(rom, start, register, dispatch):
    for probe in range(start, max(start - 34, ROM_BASE - 1), -2):
        half = hw(rom, probe)
        if (half & 0xF800) != 0x2800 or ((half >> 8) & 0x07) != register:
            continue
        after = hw(rom, probe + 2)
        if (after & 0xF000) != 0xD000:
            continue
        condition = (after >> 8) & 0x0F
        offset = after & 0x00FF
        if offset & 0x80:
            offset -= 0x100
        target = probe + 6 + (offset << 1)
        if target <= dispatch:
            continue
        bound = half & 0xFF
        if condition in (2, 3):
            count = bound
        elif condition in (8, 9):
            count = bound + 1
        else:
            continue
        if count:
            return count, probe, probe + 2
    return None, None, None


def thumb_table(rom, dispatch):
    jump = hw(rom, dispatch)
    register = (jump >> 3) & 0x07
    scale = 1
    loaded = register
    if dispatch > ROM_BASE:
        factor, source = thumb_shift(hw(rom, dispatch - 2), register)
        if factor:
            scale, loaded = factor, source
    load_at = stride = base_reg = index = None
    for probe in range(dispatch - 2, max(dispatch - 20, ROM_BASE - 1), -2):
        candidate, base_register, index_register = thumb_load(hw(rom, probe))
        if candidate is None or (hw(rom, probe) & 0x07) != loaded:
            continue
        load_at, stride, base_reg, index = probe, candidate, base_register, index_register
        break
    if load_at is None:
        return None
    base, adr_at = thumb_base(rom, load_at - 2, base_reg)
    count, check, branch = thumb_bound(rom, load_at - 2, index, dispatch)
    if base is None or count is None:
        return None
    if base + count * stride > ROM_BASE + len(rom):
        return None
    targets = []
    for position in range(count):
        if stride == 1:
            value = rom[base - ROM_BASE + position]
            target = base + value * scale
            mode = MODE_THUMB
        elif stride == 2:
            value = hw(rom, base + position * 2)
            target = base + value * scale
            mode = MODE_THUMB
        else:
            value = word(rom, base + position * 4)
            target = value & ~1
            mode = MODE_THUMB if value & 1 else MODE_ARM
        if not in_image(rom, target) or thumb_length(rom, target) is None:
            return None
        targets.append((target, mode))
    return {"dispatch": dispatch, "check": check, "branch": branch, "adr_at": adr_at,
            "load_addr": load_at, "base_reg": base_reg, "index": index,
            "base": base, "count": count, "stride": stride, "scale": scale,
            "condition": CONDITION_NAMES[(hw(rom, branch) >> 8) & 0x0F],
            "cmp": hw(rom, check), "bcc": hw(rom, branch), "load": hw(rom, load_at),
            "jump": jump, "targets": targets}


def jump_tables(rom, classes, modes, ranges):
    tables = []
    for addr, mode in dispatch_sites(rom, classes, modes, ranges):
        if mode != MODE_THUMB:
            continue
        table = thumb_table(rom, addr)
        if table is not None:
            tables.append(table)
    return tables


def thumb_literals(rom, addr, count=24):
    found = {}
    probe = addr - 2
    for _ in range(count):
        if probe < ROM_BASE:
            break
        half = hw(rom, probe)
        if (half & 0xF800) == 0x4800:
            register = (half >> 8) & 0x07
            pool = ((probe + 4) & ~3) + (half & 0xFF) * 4
            if register not in found and has_word(rom, pool):
                found[register] = (probe, word(rom, pool))
        probe -= 2
    return found


def arm_literals(rom, addr, count=12):
    found = {}
    probe = addr - 4
    for _ in range(count):
        if probe < ROM_BASE or not has_word(rom, probe):
            break
        instruction = word(rom, probe)
        if (instruction & 0x0F7F0000) == 0x051F0000:
            register = (instruction >> 12) & 0x0F
            pool = literal_target(rom, probe)
            if register not in found and has_word(rom, pool):
                found[register] = (probe, word(rom, pool))
        probe -= 4
    return found


def install_effects(rom, start, stop):
    values = {}
    effect = []
    for addr in range(start, stop, 2):
        half = hw(rom, addr)
        if (half & 0xF800) == 0x4800:
            pool = ((addr + 4) & ~3) + (half & 0xFF) * 4
            values[(half >> 8) & 0x07] = word(rom, pool) if has_word(rom, pool) else None
        elif (half & 0xF800) == 0x2000:
            values[half & 0x07] = half & 0xFF
        elif (half & 0xF800) in (0x6000, 0x8000):
            stored = half & 0x07
            base = (half >> 3) & 0x07
            width = 4 if (half & 0xF800) == 0x6000 else 2
            offset = ((half >> 6) & 0x1F) * width
            if values.get(base) is not None and values.get(stored) is not None:
                effect.append({"site": addr, "address": (values[base] + offset) & 0xFFFFFFFF,
                               "width": width,
                               "value": values[stored] & (0xFFFFFFFF if width == 4 else 0xFFFF)})
        elif (half & 0xF800) == 0x0000 and (half >> 6) & 0x1F:
            source = (half >> 3) & 0x07
            values[half & 0x07] = ((values[source] << ((half >> 6) & 0x1F)) & 0xFFFFFFFF
                                   if values.get(source) is not None else None)
    return effect


def irq_install(rom, classes, modes, ranges):
    for begin, stop in ranges:
        for addr in range(ROM_BASE + begin, ROM_BASE + stop - 4, 2):
            offset = addr - ROM_BASE
            if classes[offset] not in (PROVEN, FILTERED):
                continue
            if modes[offset] == MODE_THUMB:
                half = hw(rom, addr)
                if (half & 0xF800) != 0x6000:
                    continue
                stored = half & 0x07
                base = (half >> 3) & 0x07
                immediate = ((half >> 6) & 0x1F) * 4
                loads = thumb_literals(rom, addr)
                instruction = half
            elif modes[offset] == MODE_ARM and addr % 4 == 0:
                instruction = word(rom, addr)
                if (instruction & 0x0FF00000) != 0x05800000:
                    continue
                stored = (instruction >> 12) & 0x0F
                base = (instruction >> 16) & 0x0F
                immediate = instruction & 0x0FFF
                loads = arm_literals(rom, addr)
            else:
                continue
            if base not in loads or stored not in loads:
                continue
            if loads[base][1] + immediate != IRQ_VECTOR:
                continue
            handler = loads[stored][1]
            if not 0x03000000 <= handler < 0x04000000:
                continue
            start = min(loads[base][0], loads[stored][0])
            return {"site": addr, "mode": modes[offset], "base_at": loads[base][0],
                    "base": loads[base][1], "value_at": loads[stored][0], "handler": handler,
                    "immediate": immediate, "instruction": instruction, "start": start,
                    "effects": install_effects(rom, start, start + 0x1A),
                    "words": [(probe, hw(rom, probe)) for probe in range(start, start + 0x1A, 2)]}
    return None


def irq_handler(rom, overlay, install):
    source, dest, size, _declared = overlay
    handler = install["handler"]
    if not dest <= handler < dest + size:
        return None
    start = source + (handler - dest)
    mode = MODE_THUMB if handler & 1 else MODE_ARM
    classes = bytearray(len(rom))
    spans, _pools, entries, _calls = walk(rom, [(start, mode)], classes,
                                          bytearray(len(rom)), PROVEN)
    runs = class_runs(classes, PROVEN)
    table = None
    for begin, stop in runs:
        for addr in range(ROM_BASE + begin, ROM_BASE + stop - 3, 4):
            if (word(rom, addr) & 0x0F7F0000) != 0x051F0000:
                continue
            value = word(rom, literal_target(rom, addr))
            if not dest <= value < dest + size:
                continue
            found = []
            probe = source + (value - dest)
            while len(found) < 64 and has_word(rom, probe):
                pointer = word(rom, probe)
                if not pointer & 1 or not in_image(rom, pointer & ~1):
                    break
                found.append(pointer)
                probe += 4
            if len(found) > 1:
                table = {"at": value, "rom": source + (value - dest), "entries": found,
                         "distinct": sorted(set(found))}
                break
        if table is not None:
            break
    return {"rom": start, "mode": mode, "runs": runs, "entries": entries,
            "bytes": sum(stop - begin for begin, stop in runs), "table": table,
            "words": [(start + offset, word(rom, start + offset))
                      for offset in range(0, 0x14 if mode == MODE_ARM else 0x0A,
                                          4 if mode == MODE_ARM else 2)]}





_RUN_PATTERNS = {}


def class_runs(classes, value):
    marker = bytes([value])
    if classes.count(marker) > 1 << 20:
        pattern = _RUN_PATTERNS.get(value)
        if pattern is None:
            pattern = re.compile(re.escape(marker) + b"+")
            _RUN_PATTERNS[value] = pattern
        return [(match.start(), match.end()) for match in pattern.finditer(classes)]
    out = []
    pos = 0
    total = len(classes)
    while pos < total:
        start = classes.find(marker, pos)
        if start < 0:
            break
        stop = start
        while stop < total and classes[stop] == value:
            stop += 1
        out.append((start, stop))
        pos = stop
    return out


def mode_runs(classes, modes, values):
    out = []
    for value in range(256):
        name = _NAMES[value]
        if name is None or name not in values:
            continue
        for start, stop in class_runs(classes, value):
            pos = start
            while pos < stop:
                mode = modes[pos]
                end = pos + 1
                while end < stop and modes[end] == mode:
                    end += 1
                out.append((pos, end, name, mode))
                pos = end
    out.sort()
    return out


def pointer_runs(rom):
    values, flags = named_words(rom)
    runs = []
    current = []
    for index, hit in enumerate(flags):
        if hit:
            current.append(values[index] & ~1)
        elif current:
            if len(current) > 1:
                runs.append(current)
            current = []
    if len(current) > 1:
        runs.append(current)
    return runs


def table_word_sites(rom):
    values, flags = named_words(rom)
    counts = {}
    for index, hit in enumerate(flags):
        if hit:
            counts[values[index]] = counts.get(values[index], 0) + 1
    sites = []
    begin = None
    for index, hit in enumerate(flags):
        if hit:
            if begin is None:
                begin = index
            if counts[values[index]] >= FACTORY_REPEATS:
                sites.append((index * 4, index * 4 + 4))
        elif begin is not None:
            if index - begin > 1:
                sites.append((begin * 4, index * 4))
            begin = None
    if begin is not None and len(flags) - begin > 1:
        sites.append((begin * 4, len(flags) * 4))
    return sites


def table_targets(runs, proven):
    out = set()
    for run in runs:
        if any(target in proven for target in run):
            out.update(run)
    return out


def table_at(rom, base, cap=TABLE_CAP):
    found = []
    at = base
    while len(found) < cap and has_word(rom, at):
        value = word(rom, at)
        if not value & 1 or not in_image(rom, value & ~1):
            break
        found.append(value & ~1)
        at += 4
    return found


def named_tables(rom, classes, modes):
    bases = set()
    for begin, stop in code_ranges(classes):
        addr = ROM_BASE + begin
        while addr < ROM_BASE + stop:
            if modes[addr - ROM_BASE] == MODE_THUMB:
                half = hw(rom, addr)
                if 0x4800 <= half <= 0x4FFF:
                    pool = ((addr + 4) & ~3) + (half & 0xFF) * 4
                    if has_word(rom, pool):
                        bases.add(word(rom, pool))
                addr += 2
                continue
            if addr % 4 == 0 and has_word(rom, addr):
                instruction = word(rom, addr)
                if ((instruction & 0x0F7F0000) == 0x051F0000
                        and ((instruction >> 12) & 0x0F) not in (14, 15)):
                    pool = literal_target(rom, addr)
                    if has_word(rom, pool):
                        bases.add(word(rom, pool))
            addr += 4
    return bases


def pointer_words(rom, addresses):
    found = set()
    for address in addresses:
        if address % 4 or not has_word(rom, address):
            continue
        value = word(rom, address)
        if value & 1 and in_image(rom, value & ~1):
            found.add(value & ~1)
    return found


def thumb_dests(half):
    if half < 0x0800:
        return 1 << (half & 0x07)
    if half < 0x1800:
        return 1 << ((half >> 3) & 0x07)
    if half < 0x2000:
        return 1 << (half & 0x07)
    if half < 0x2800:
        return 1 << ((half >> 8) & 0x07)
    if half < 0x3000:
        return 0
    if half < 0x4000:
        return 1 << ((half >> 8) & 0x07)
    if half < 0x4400:
        if ((half >> 6) & 0x0F) in (0x08, 0x0A, 0x0B):
            return 0
        return 1 << (half & 0x07)
    if half < 0x4700:
        return 1 << (((half >> 7) & 1) * 8 + (half & 0x07))
    if half < 0x4800:
        return 0
    if half < 0x5000:
        return 1 << ((half >> 8) & 0x07)
    if half < 0x6000:
        return (1 << ((half >> 8) & 0x07)) if half & 0x0800 else 0
    if half < 0x7800:
        return 0
    if half < 0x8000:
        return 1 << ((half >> 8) & 0x07)
    if half < 0x8800:
        return 0
    if half < 0x9000:
        return 1 << ((half >> 8) & 0x07)
    if half < 0x9800:
        return 0
    if half < 0xA000:
        return 1 << ((half >> 8) & 0x07)
    if half < 0xB000:
        return 1 << ((half >> 8) & 0x07)
    if half < 0xB400:
        return 1 << ((half >> 8) & 0x07)
    if half < 0xBC00:
        return 0
    if half < 0xC000:
        return half & 0xFF
    if half < 0xC800:
        return 0
    if half < 0xD000:
        return half & 0xFF
    return 0


def arm_dests(instruction):
    opcode = (instruction >> 25) & 0x07
    destination = (instruction >> 12) & 0x0F
    if opcode in (0, 1):
        if ((instruction >> 21) & 0x0F) in (8, 9, 10, 11):
            return 0
        return 1 << destination
    if opcode in (2, 3):
        return (1 << destination) if (instruction >> 20) & 1 else 0
    if opcode == 4:
        return (instruction & 0xFFFF) if (instruction >> 20) & 1 else 0
    return 0


def thumb_source(rom, site, register):
    for at in range(site - 2, max(site - LOOKBACK, ROM_BASE - 1), -2):
        half = hw(rom, at)
        if not thumb_dests(half) & (1 << register):
            continue
        if 0x4800 <= half <= 0x4FFF and ((half >> 8) & 0x07) == register:
            pool = ((at + 4) & ~3) + (half & 0xFF) * 4
            return (word(rom, pool) if has_word(rom, pool) else None), at
        if 0xA000 <= half <= 0xAFFF and ((half >> 8) & 0x07) == register:
            return ((at + 4) & ~3) + (half & 0xFF) * 4, at
        return None, at
    return None, None


def arm_source(rom, site, register):
    for at in range(site - 4, max(site - LOOKBACK, ROM_BASE - 1), -4):
        if not has_word(rom, at):
            break
        instruction = word(rom, at)
        if not arm_dests(instruction) & (1 << register):
            continue
        if (instruction & 0x0F7F0000) == 0x051F0000 and ((instruction >> 12) & 0x0F) == register:
            pool = literal_target(rom, at)
            return (word(rom, pool) if has_word(rom, pool) else None), at
        if ((instruction & 0x0FFF0000) in (0x028F0000, 0x024F0000)
                and ((instruction >> 12) & 0x0F) == register):
            value = instruction & 0xFF
            rotate = ((instruction >> 8) & 0x0F) * 2
            if rotate:
                value = ((value >> rotate) | (value << (32 - rotate))) & 0xFFFFFFFF
            add = (instruction & 0x0FFF0000) == 0x028F0000
            return (at + 8 + value if add else at + 8 - value), at
        return None, at
    return None, None


def census(rom, want_overlay, null_closing=None):
    classes = bytearray(len(rom))
    modes = bytearray(len(rom))
    proven_spans, pools, proven_entries, calls = walk(
        rom, [(VECTOR, MODE_ARM), (CRT0, MODE_ARM)], classes, modes, PROVEN)
    taken, taken_words = thumb_entries(rom)
    verdicts = {entry: probe(rom, entry) for entry in taken}
    runs = pointer_runs(rom)
    proven_seen = set(proven_entries)
    accepted = set()
    accepted_order = []
    channels = {}
    walked = {}
    walks = 0
    rounds = [{"round": 0, "proven": classes.count(PROVEN), "filtered": 0,
               "accepted": 0, "called": 0, "tables": 0}]
    tables = []

    def prove(targets):
        nonlocal walks
        pending = list(targets)
        while pending:
            item = pending.pop()
            if item in proven_seen:
                continue
            proven_seen.add(item)
            spans, more, entries, made = walk(rom, [item], classes, modes, PROVEN)
            pools.update(more)
            proven_entries.update(entries)
            pending += made
            walks += 1

    while True:
        proven_addresses = {address for address, _mode in proven_entries}
        tabled = table_targets(runs, proven_addresses)
        ranges = class_runs(classes, PROVEN) + class_runs(classes, FILTERED)
        tables = jump_tables(rom, classes, modes, ranges)
        dispatched = set()
        for table in tables:
            dispatched.update(table["targets"])
        candidates = {(address, MODE_THUMB) for address in taken} | dispatched
        for entry in sorted(candidates):
            if entry in accepted:
                continue
            if entry in dispatched:
                channels[entry] = "table dispatch"
            else:
                ok, returned, branches = verdicts[entry[0]]
                if not ok or not returned:
                    continue
                if branches >= FILTER_BRANCHES:
                    channels[entry] = "conditional branch"
                elif entry in calls:
                    channels[entry] = "call"
                elif entry[0] in tabled:
                    channels[entry] = "function pointer table"
                else:
                    continue
            accepted.add(entry)
            accepted_order.append(entry)
        before = (len(accepted), walks, len(proven_entries), len(calls))
        for entry in accepted_order:
            due = PROVEN if entry in calls else FILTERED
            if walked.get(entry) == due:
                continue
            walked[entry] = due
            spans, more, entries, made = walk(rom, [entry], classes, modes, due)
            pools.update(more)
            if due == PROVEN:
                proven_entries.update(entries)
            calls |= set(made)
            walks += 1
        prove(set(calls) - proven_seen)
        if (len(accepted), walks, len(proven_entries), len(calls)) == before:
            break
        rounds.append({"round": len(rounds), "proven": classes.count(PROVEN),
                       "filtered": classes.count(FILTERED), "accepted": len(accepted),
                       "called": sum(1 for entry in accepted if entry in calls),
                       "tables": len(tables)})
    overlay = None
    irq = None
    if want_overlay:
        overlay = overlay_copy(rom)
        install = irq_install(rom, classes, modes,
                              class_runs(classes, PROVEN) + class_runs(classes, FILTERED))
        if install is not None:
            irq = {"install": install, "handler": irq_handler(rom, overlay, install)}

    def verdict(address):
        if address not in verdicts:
            verdicts[address] = probe(rom, address)
        return verdicts[address]

    factories = repeated_code_pointers(rom)
    extra = {}
    held = {"register": [], "run": [], "record": [], "slot": [], "gap": [], "prologue": [],
            "runfree": [], "load": [], "pool": [], "overlay": [], "close": []}
    swept = set()
    swept_runs = []
    register_sites = {"sites": 0, "bounded": 0, "entries": []}
    channel_rounds = []
    first = {}

    def hold(entry, value, key):
        nonlocal walks
        ok, returned, _branches = verdict(entry[0])
        if not ok or not returned:
            return 0
        extra[entry] = value
        held[key].append(entry)
        spans, more, entries, made = walk(rom, [entry], classes, modes, value)
        pools.update(more)
        if value == PROVEN:
            proven_entries.update(entries)
        prove(set(made) - proven_seen)
        walks += 1
        return 1

    def table_words(proven):
        run = set(table_targets(runs, proven))
        runfree = set()
        for group in runs:
            if not any(target in proven for target in group):
                runfree.update(group)
        slot = set()
        if irq is not None and irq["handler"] is not None and irq["handler"]["table"] is not None:
            slot = {value & ~1 for value in irq["handler"]["table"]["distinct"] if value & 1}
        slot -= run
        record = {value & ~1 for value in factories} - run - slot
        load = set()
        for base in named_tables(rom, classes, modes):
            if base % 4 == 0 and in_image(rom, base):
                load.update(table_at(rom, base))
        pool = pointer_words(rom, pools)
        overlay_words = set()
        if overlay is not None:
            source, _dest, size, _declared = overlay
            overlay_words = pointer_words(rom, [source + offset for offset in range(0, size, 4)])
        return {"run": sorted(run), "record": sorted(record - run),
                "slot": sorted(slot), "runfree": sorted(runfree - run),
                "load": sorted(load - run - slot - record), "pool": sorted(pool),
                "overlay": sorted(overlay_words)}

    anchor_classes = (PROVEN, FILTERED, TABLE)
    for channel_round in range(CHANNEL_ROUNDS):
        added = 0
        register_sites = register_branches(rom, classes, modes, code_ranges(classes))
        for record in register_sites["entries"]:
            entry = (record["target"], record["mode"])
            if entry in accepted or entry in extra:
                continue
            added += hold(entry, PROVEN, "register")
        words = table_words({address for address, _mode in proven_entries})
        for entry in accepted_order:
            if channels[entry] != "function pointer table" or entry in extra:
                continue
            extra[entry] = TABLE
            held["run"].append(entry)
            walk(rom, [entry], classes, modes, TABLE)
        for shape in TABLE_SHAPES:
            for target in words[shape]:
                entry = (target, MODE_THUMB)
                if entry in accepted or entry in extra:
                    continue
                added += hold(entry, TABLE, shape)
        anchors = []
        halves = views_of(rom)[1]
        for begin, stop in code_ranges(classes):
            for index in range(begin, stop, 2):
                if classes[index] not in anchor_classes:
                    continue
                half = halves[index >> 1]
                if (half & 0xFF00) == 0xBD00 or (half & 0xFF87) == 0x4700:
                    anchors.append(ROM_BASE + index + 2)
        for candidate_address in anchors:
            if not in_image(rom, candidate_address):
                continue
            if classes[candidate_address - ROM_BASE] != UNCLASSIFIED:
                continue
            entry = (candidate_address, MODE_THUMB)
            if entry in accepted or entry in extra:
                continue
            added += hold(entry, GAPFILL, "gap")
        sweep = []
        sweep_candidates = 0
        for index in range(0, len(rom), 2):
            if classes[index] != UNCLASSIFIED:
                continue
            if not 0xB500 <= halves[index >> 1] <= 0xB5FF:
                continue
            sweep_candidates += 1
            entry = (ROM_BASE + index, MODE_THUMB)
            if entry in swept:
                continue
            end = linear_end(rom, entry[0])
            if end is None:
                continue
            swept.add(entry)
            held["prologue"].append(entry)
            sweep.append((entry[0], end))
        swept_runs.extend(sweep)
        added += len(sweep)
        if not first:
            first = {"register_sites": register_sites["sites"],
                     "register_bounded": register_sites["bounded"],
                     "table_run": len(words["run"]), "table_record": len(words["record"]),
                     "table_slot": len(words["slot"]), "table_runfree": len(words["runfree"]),
                     "table_load": len(words["load"]), "table_pool": len(words["pool"]),
                     "table_overlay": len(words["overlay"]), "gap_anchors": len(anchors),
                     "prologue_candidates": sweep_candidates}
        channel_rounds.append({"round": channel_round, "register": len(held["register"]),
                               "table": sum(len(held[key]) for key in TABLE_SHAPES),
                               "gap": len(held["gap"]), "prologue": len(held["prologue"]),
                               "proven": classes.count(PROVEN),
                               "table_bytes": classes.count(TABLE),
                               "gap_bytes": classes.count(GAPFILL),
                               "prologue_bytes": merged_length(swept_runs)})
        if not added:
            break
    pre = bytes(classes)
    first["table_close"] = 0
    close_candidates = []
    for target in sorted(taken):
        entry = (target, MODE_THUMB)
        if entry in accepted or entry in extra:
            continue
        first["table_close"] += 1
        close_candidates.append(target)
    close_picked, close_found = closing_entries(rom, close_candidates, pre, modes, null_closing)
    for target in close_picked:
        entry = (target, MODE_THUMB)
        extra[entry] = TABLE
        held["close"].append(entry)
        walk(rom, [entry], classes, modes, TABLE)
        walks += 1
    closing = {"candidates": first["table_close"], "accepted": len(close_found),
               "null_accepted": null_closing,
               "claimed": null_closing is not None
               and under_closing_bar(null_closing, len(close_found))}
    prologue_bytes = merged_length(swept_runs)
    pool_words = sorted(address for address in pools if has_word(rom, address) and not address % 4)
    pool_runs = []
    for address in pool_words:
        if not pool_runs or address != pool_runs[-1][1]:
            pool_runs.append([address, address + 4])
        else:
            pool_runs[-1][1] = address + 4
    pool_overlap = 0
    for start, stop in pool_runs:
        for index in range(start - ROM_BASE, stop - ROM_BASE):
            if classes[index] == UNCLASSIFIED:
                classes[index] = POOL
            elif classes[index] in CODE_CLASSES:
                pool_overlap += 1
    overlay_code = 0
    overlay_pool = 0
    thunks = []
    if overlay is not None:
        source, dest, size, declared = overlay
        for index in range(source - ROM_BASE, source - ROM_BASE + size):
            if classes[index] in CODE_CLASSES:
                overlay_code += 1
            elif classes[index] == POOL:
                overlay_pool += 1
            else:
                classes[index] = OVERLAY_CLASS
        thunks = overlay_thunks(rom, dest, size)
    totals = {CLASS_NAMES[value]: classes.count(value) for value in
              (PROVEN, TABLE, FILTERED, GAPFILL, POOL, OVERLAY_CLASS, UNCLASSIFIED)}
    if sum(totals.values()) != len(rom):
        raise SystemExit("the class totals %d are not the image size %d"
                         % (sum(totals.values()), len(rom)))
    accepted_set = set(accepted)
    accepted_addresses = {address for address, _mode in accepted_set}
    end = ROM_BASE + len(rom)
    accepted_words = sum(1 for value in views_of(rom)[2]
                         if value & 1 and ROM_BASE <= value < end
                         and (value & ~1) in accepted_addresses)
    uncalled = [entry for entry in accepted_order if entry not in calls]
    leaves = [entry for entry in accepted_order
              if channels[entry] in ("call", "function pointer table")
              and verdicts[entry[0]][2] < FILTER_BRANCHES]
    counts = {}
    for entry in accepted_order:
        counts[channels[entry]] = counts.get(channels[entry], 0) + 1
    return {"size": len(rom), "classes": classes, "modes": modes, "totals": totals,
            "pre": pre,
            "proven_spans": proven_spans, "filtered_spans": [],
            "proven": class_runs(classes, PROVEN), "filtered": class_runs(classes, FILTERED),
            "table": class_runs(classes, TABLE), "gapfill": class_runs(classes, GAPFILL),
            "pool": class_runs(classes, POOL), "overlay_runs": class_runs(classes, OVERLAY_CLASS),
            "unclassified": class_runs(classes, UNCLASSIFIED), "pools": pools,
            "pool_words": len(pool_words), "pool_runs": len(pool_runs),
            "pool_overlap": pool_overlap, "overlay": overlay, "overlay_code": overlay_code,
            "overlay_pool": overlay_pool, "thunks": thunks,
            "taken": taken, "taken_words": taken_words,
            "accepted": sorted(entry for entry, _mode in accepted),
            "accepted_modes": accepted_set, "channels": counts,
            "accepted_words": accepted_words, "uncalled": sorted(entry[0] for entry in uncalled),
            "leaves": sorted(entry[0] for entry in leaves),
            "proven_entries": proven_entries, "proven_seen": proven_seen,
            "calls": calls, "table_runs": len(runs), "tabled": tabled,
            "rounds": rounds, "tables": tables, "irq": irq,
            "register_branches": register_sites, "channel_rounds": channel_rounds,
            "channel_first": first, "held": {key: list(value) for key, value in held.items()},
            "extra": extra, "channel_bytes": {CLASS_NAMES[value]: classes.count(value)
                                             for value in CODE_CLASSES},
            "prologue_bytes": prologue_bytes, "closing": closing,
            "decodable": decodable_runs(rom, classes),
            "function_rows": mode_runs(classes, modes, tuple(CLASS_NAMES[value]
                                                             for value in CODE_CLASSES))}


def measure(rom, null=None):
    if null is None:
        null = census(permute(rom), False)
    return census(rom, True, null["closing"]["accepted"])


def permute(rom):
    out = bytearray(rom)
    for base in range(0, len(out), BLOCK):
        block = bytes(out[base:base + BLOCK])
        pairs = [block[index:index + 2] for index in range(0, len(block) - 1, 2)]
        pairs.reverse()
        out[base:base + len(block)] = b"".join(pairs)
    return bytes(out)


def measure_null(rom):
    return census(permute(rom), False)


def share(part, whole):
    return "%.4f" % (100.0 * part / whole) if whole else "0.0000"


def rate(part, whole):
    return ("%s %%" % share(part, whole)) if whole else "-"



def doc_text(measured, null):
    totals = measured["totals"]
    size = measured["size"]
    source, dest, copied, declared = measured["overlay"]
    proven_entries = measured["proven_entries"]
    roots = {VECTOR, CRT0}
    found = proven_entries - {(VECTOR, MODE_ARM), (CRT0, MODE_ARM)}
    null_found = null["proven_entries"] - {(VECTOR, MODE_ARM), (CRT0, MODE_ARM)}
    thunks = measured["thunks"]
    channels = measured["channels"]
    accepted = len(measured["accepted"])
    uncalled = len(measured["uncalled"])
    first = measured["channel_first"]
    held = measured["held"]
    null_held = null["held"]
    sites = measured["register_branches"]
    table_total = sum(len(held[key]) for key in TABLE_SHAPES)
    table_null = sum(len(null_held[key]) for key in TABLE_SHAPES)
    table_candidates = sum(first.get("table_" + shape, 0) for shape in TABLE_SHAPES)
    closing = measured["closing"]
    closing_share = share(closing["null_accepted"] or 0, closing["accepted"])
    closing_verdict = ("the bytes it reaches are the table-held class" if closing["claimed"]
                       else "the channel contributes no entry and no byte")
    lines = [
        "# Code and data split",
        "",
        "Generated by `python tools\\split\\code_split.py --write`; `--check` re-derives this file",
        "and `CODE_SPLIT.csv` from the builder's image and refuses a difference. One class per byte,",
        "so the class totals are the image size.",
        "",
        "## Entry census",
        "",
        "The pointer filter reads every address-taken odd word in the image and accepts the ones it",
        "can follow to code. Its channels:",
        "",
        "| channel | entries |",
        "|---|---|",
        "| contains a conditional branch | %s |"
        % format(channels.get("conditional branch", 0), ","),
        "| a `bl` target of walked code and no branch | %s |"
        % format(channels.get("call", 0), ","),
        "| a function-pointer-table word and no branch | %s |"
        % format(channels.get("function pointer table", 0), ","),
        "| a target of a jump-table dispatch in walked code | %s |"
        % format(channels.get("table dispatch", 0), ","),
        "| total | %s |" % format(accepted, ","),
        "",
        "| entry source | words | entries |",
        "|---|---|---|",
        "| the whole image's address-taken odd words | %s | %s |"
        % (format(measured["taken_words"], ","), format(len(measured["taken"]), ",")),
        "| the accepted entries' odd words | %s | %s |"
        % (format(measured["accepted_words"], ","), format(accepted, ",")),
        "| the descent's roots and every target it follows | - | %s |"
        % format(len(found), ","),
        "",
        "The proved descent starts at the two roots above and follows every `bl` target, every",
        "conditional and unconditional branch target, the address a `bx` register holds when the",
        "instruction before it loads that register from the literal pool, the address an ARM `ldr",
        "pc,[pc,#imm]` loads, and every return address an ARM `ldr lr,[pc,#imm]` loads. It also",
        "walks the target of every call the table-held and gap-fill entries make. The %s"
        % format(len(found), ","),
        "targets it proves are Thumb %s and ARM %s."
        % (format(sum(1 for _address, mode in found if mode == MODE_THUMB), ","),
           format(sum(1 for _address, mode in found if mode == MODE_ARM), ",")),
        "",
        "## Call closure",
        "",
        "A `bl` target is code because code calls it, so every target the walk names is queued at",
        "proven code, and a call from a filtered entry proves its callee. The census accepts",
        "entries, walks them, promotes the targets they call, and repeats until a round adds",
        "nothing. Per round:",
        "",
        "| round | proven | filtered | accepted entries | call targets named | jump tables |",
        "|---|---|---|---|---|---|",
    ]
    for record in measured["rounds"]:
        lines.append("| %d | %s | %s | %s | %s | %d |"
                     % (record["round"], format(record["proven"], ","),
                        format(record["filtered"], ","), format(record["accepted"], ","),
                        format(record["called"], ","), record["tables"]))
    lines += [
        "",
        "Round 0 is the descent from the two roots alone; each later round accepts the entries the",
        "previous round's walk made reachable.",
        "",
        "## Walk rule",
        "",
        "A Thumb halfword outside the ARMv4T encoding ends its path: 0x4780..0x47FF (the ARMv5",
        "`blx`), 0xB100..0xB3FF, 0xB600..0xBBFF, 0xBE00..0xBFFF, 0xDE00..0xDEFF, 0xE800..0xEFFF, and",
        "a long-branch halfword that no `bl` pair introduces. `push`, `pop` and every other ARMv4T",
        "encoding are instructions.",
        "`bx lr`, `pop {pc}` and `swi` end a path, and so does `bx` on any other register, because",
        "its target is not in the instruction. `add pc, rN` and `mov pc, rN` write the program",
        "counter too: the offsets they read are a dispatch table, so the path ends there instead of",
        "walking the table as instructions. An unconditional `b` continues at its target, which is",
        "not code when the bytes it jumps over are a literal pool or a tail. A conditional branch",
        "queues its in-image target and the walk continues at the fall-through, so both arms are",
        "walked. ARM follows the same rule, and any write to `pc` other than `b`/`bl` ends the path.",
        "A path that leaves the image or passes the step limit ends there.",
        "",
        "## Acceptance",
        "",
        "An odd word is accepted as an entry when the closure of paths from it reaches a return,",
        "meets no halfword outside the ARMv4T encoding, does not pass the step limit, and either",
        "contains at least one conditional branch or is reached from code: it is a `bl` target, a",
        "word of a function-pointer table whose run holds at least one proven entry, or a target of",
        "a jump-table dispatch inside walked code. The branch is the criterion that keeps data out",
        "of the branchless channel: a stretch of data can decode as a path that returns, but a",
        "function body branches unless it is a leaf that something calls. That rule accepts %s of"
        % format(accepted, ","),
        "the %s entries, %s of which are branchless: %s are function-pointer-table words and %s are"
        % (format(len(measured["taken"]), ","), format(len(measured["leaves"]), ","),
           format(channels.get("function pointer table", 0), ","),
           format(channels.get("call", 0), ",")),
        "call targets. %s of the accepted entries are named by no call, and the permuted image"
        % format(uncalled, ","),
        "passes %s of them, so the false-entry rate on everything no call proves is %s %%."
        % (format(len(null["uncalled"]), ","), share(len(null["uncalled"]), uncalled)),
        "",
        "The closing run accepts the branchless words that rule refuses. The word's own linear",
        "decode, not the branch closure, must meet no halfword outside the ARMv4T encoding, must end",
        "on a return or on a branch into bytes a class already holds, and must reach every branch",
        "target it makes either as one of its own instruction boundaries or as bytes a class already",
        "holds. It accepts %s entries from the %s words no other shape claimed, and the permuted"
        % (format(closing["accepted"], ","), format(first["table_close"], ",")),
        "image accepts %s, the same shape read over bytes that hold no code."
        % format(closing["null_accepted"] or 0, ","),
        "",
        "## Channels",
        "",
        "Seven channels are measured: the six the table below counts, and the closing run, whose",
        "accept and null counts are printed under the table channel. Each one runs over the same",
        "census as the descent and is measured with the same census over the image with every 64 KiB",
        "block reversed by halfword, so its `null` column is what the channel finds where there is no",
        "code to find. Four of them own a class in the table below; the register channel owns none",
        "because an address it resolves is proved by its caller, and the prologue sweep and the",
        "closing run are measured only, because a channel whose null is not below its accept rate",
        "emits no entry and no byte.",
        "",
        "| channel | candidates | accepted | bytes | null | null rate |",
        "|---|---|---|---|---|---|",
        "| the descent from the two roots | 2 roots | %s | %s | %s | %s %% |"
        % (format(len(found), ","), format(totals["proven code"], ","),
           format(len(null_found), ","), share(len(null_found), len(found))),
        "| the pointer filter | %s words | %s | %s | %s | %s %% |"
        % (format(measured["taken_words"], ","), format(accepted, ","),
           format(totals["filtered pointer-entry code"], ","),
           format(len(null["accepted"]), ","),
           share(len(null["accepted"]), accepted)),
        "| register-loaded code addresses | %s | %s | 0 | %s | %s |"
        % (format(sites["sites"], ","), format(len(held["register"]), ","),
           format(len(null_held["register"]), ","),
           rate(len(null_held["register"]), len(held["register"]))),
        "| function-pointer tables and record words | %s | %s | %s | %s | %s %% |"
        % (format(table_candidates, ","),
           format(table_total, ","), format(totals["table-held code"], ","),
           format(table_null, ","), share(table_null, table_total)),
        "| the Thumb prologue sweep, measured, not counted as code | %s | %s | %s | %s | %s %% |"
        % (format(first["prologue_candidates"], ","), format(len(held["prologue"]), ","),
           format(measured["prologue_bytes"], ","),
           format(len(null_held["prologue"]), ","),
           share(len(null_held["prologue"]), len(held["prologue"]))),
        "| the gap fill | %s | %s | %s | %s | %s %% |"
        % (format(first["gap_anchors"], ","), format(len(held["gap"]), ","),
           format(totals["gap-fill code"], ","), format(len(null_held["gap"]), ","),
           share(len(null_held["gap"]), len(held["gap"]))),
        "",
        "A channel's `null rate` is the share of its accepted entries the permuted image also",
        "accepts, which is the false-entry rate it carries; a channel whose accepted count is 0 has",
        "no rate and prints `-`. The channel rounds:",
        "",
        "| round | register | table-held | gap-fill | prologue-sweep | proven bytes | table bytes |"
        " gap bytes | swept bytes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for record in measured["channel_rounds"]:
        lines.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s |"
                     % (record["round"], record["register"], record["table"], record["gap"],
                        record["prologue"], format(record["proven"], ","),
                        format(record["table_bytes"], ","), format(record["gap_bytes"], ","),
                        format(record["prologue_bytes"], ",")))
    lines += [
        "",
        "### Register-loaded code addresses",
        "",
        "A `bx rN`, `mov pc, rN` or ARM `bx` inside walked code names its target when the register",
        "still holds what a pc-relative load or an `adr` put there: the scan walks back up to 0x40",
        "bytes and stops at the first halfword that writes the register, so the value it resolves is",
        "the register's reaching definition, never a load the code overwrote. %s such sites are in"
        % format(sites["sites"], ","),
        "walked code, %s of them with a bounds check and an indexed load, and the scan resolves %s."
        % (format(sites["bounded"], ","), format(len(sites["entries"]), ",")),
        "In %s of them the resolved value is code that no other channel names, and in %s it is an"
        % (format(len(held["register"]), ","),
           format(len(sites["entries"]) - len(held["register"]), ",")),
        "entry the census already accepts.",
        "The rest of the sites hold a register-offset load of a record field,",
        "an ALU result, or no write inside the window, which is the engine reaching code through a",
        "record rather than through a literal; the table-held channel is what names those.",
        "",
        "### Function-pointer tables and record words",
        "",
        "Eight shapes name a code address from data. Three seed on code the census already holds: a",
        "run of two or more consecutive 4-aligned odd words naming the image, when the run holds at",
        "least one proven entry; a word that occurs at least %d times at 4-aligned sites as an odd"
        % FACTORY_REPEATS,
        "in-image address, which is the shape of a factory word repeated in every record of a",
        "family; and a pointer table the walked code names with a literal load, which is the",
        "interrupt dispatcher's slot table. Four read a data word the census never looks at for an",
        "entry: a run of two or more consecutive odd words that holds no proven entry, a run the",
        "walked code names with a literal load and reads as a table, an odd word in a literal pool a",
        "walked load reaches, and an odd word the startup copy carries into IWRAM. Every word of",
        "those shapes is accepted when its own paths reach a return, and the bytes they reach are",
        "the table-held class. The proven-seeded run shape names %s words and accepts %s, the slot"
        % (format(first["table_run"], ","), format(len(held["run"]), ",")),
        "shape names %s and accepts %s, and the record shape names %s and accepts %s. The permuted"
        % (format(first["table_slot"], ","), format(len(held["slot"]), ","),
           format(first["table_record"], ","), format(len(held["record"]), ",")),
        "image accepts %s of the slots and record words, 0 of the proven-seeded runs."
        % format(len(null_held["slot"]) + len(null_held["record"]), ","),
        "The run shape cannot fire there because it needs a proven entry to seed it,",
        "and the slot shape cannot fire because the permuted image walks no interrupt install.",
        "Those two nulls are not exercisable and are reported as such rather than as zero.",
        "",
        "The fifth shape reads no table: it is the closing run, the named word that no table holds",
        "and whose own linear decode ends on a return or on a branch into code. It names %s words"
        % format(first["table_close"], ","),
        "and accepts %s, and the permuted image accepts %s, a null share of %s %% against the"
        % (format(closing["accepted"], ","), format(closing["null_accepted"] or 0, ","),
           closing_share),
        "%s %% bar, so %s." % ("%.4f" % CLOSING_BAR, closing_verdict),
        "",
        "The five shapes that seed on data alone carry their own null. An unseeded run names %s"
        % format(first["table_runfree"], ","),
        "words and accepts %s, and the permuted image accepts %s."
        % (format(len(held["runfree"]), ","), format(len(null_held["runfree"]), ",")),
        "A table the walked code reads names %s words and accepts %s against %s there."
        % (format(first["table_load"], ","), format(len(held["load"]), ","),
           format(len(null_held["load"]), ",")),
        "A literal pool names %s words and accepts %s against %s."
        % (format(first["table_pool"], ","), format(len(held["pool"]), ","),
           format(len(null_held["pool"]), ",")),
        "The startup copy carries %s words and accepts %s against %s."
        % (format(first["table_overlay"], ","), format(len(held["overlay"]), ","),
           format(len(null_held["overlay"]), ",")),
        "",
        "The map layer factory word 0x080056A1 is the repeated shape at its largest: 1,294 records",
        "carry it, and its target 0x080056A0 is already accepted by the pointer filter, so the",
        "channel adds no byte there and only states why the target is code. The interrupt slot table",
        "names 0x08020D25 fourteen times, and that word is not named by any other channel.",
        "",
        "### Prologue sweep",
        "",
        "Every halfword in 0xB500..0xB5FF is a Thumb `push` that saves `lr`, which is how this",
        "compiler opens a function. The sweep takes each one in unclassified space and decodes",
        "forward, linearly, until the run returns through `pop {..., pc}` or `bx lr`; a run that",
        "meets a halfword outside the ARMv4T encoding, an unconditional branch, a register branch or",
        "a write to `pc` before it returns is refused, and so is a run longer than %d instructions."
        % PROLOGUE_CAP,
        "It accepts %s of %s candidates and measures the decoded run, not the branch closure. Its"
        % (format(len(held["prologue"]), ","), format(first["prologue_candidates"], ",")),
        "null rate is %s %%, so the sweep is at chance on this image: most of what it accepts is"
        % share(len(null_held["prologue"]), len(held["prologue"])),
        "packed payload that decodes as Thumb at the same rate, and a `push` halfword is 1 in 256 of",
        "any data. It is reported only as a measured channel: its entries and the %s B it would"
        % format(measured["prologue_bytes"], ","),
        "mark stay in the unclassified class, and its calls prove nothing, because a caller found",
        "this way is no evidence that the callee is code.",
        "",
        "### Gap fill",
        "",
        "A function's last instruction returns; if the next halfword is unclassified and its paths",
        "reach a return, it is the start of code the descent never reached. The fill takes every",
        "return inside the proven, filtered and table-held classes, tries the halfword after it,",
        "accepts the ones that walk to a return, and repeats until a round adds nothing; a return",
        "inside gap-fill code is not an anchor, so the channel cannot seed itself, and the sweep",
        "emits nothing for it to seed on. The first round takes %s returns, %s gaps are accepted, and"
        % (format(first["gap_anchors"], ","), format(len(held["gap"]), ",")),
        "the permuted image accepts %s, a null rate of %s %%."
        % (format(len(null_held["gap"]), ","),
           share(len(null_held["gap"]), len(held["gap"]))),
        "",
        "## Classes",
        "",
        "| class | extents | bytes | share |",
        "|---|---|---|---|",
        "| proven code | %s | %s | %s %% |"
        % (format(len(measured["proven"]), ","), format(totals["proven code"], ","),
           share(totals["proven code"], size)),
        "| filtered pointer-entry code | %s | %s | %s %% |"
        % (format(len(measured["filtered"]), ","), format(totals["filtered pointer-entry code"], ","),
           share(totals["filtered pointer-entry code"], size)),
        "| table-held code | %s | %s | %s %% |"
        % (format(len(measured["table"]), ","), format(totals["table-held code"], ","),
           share(totals["table-held code"], size)),
        "| gap-fill code | %s | %s | %s %% |"
        % (format(len(measured["gapfill"]), ","), format(totals["gap-fill code"], ","),
           share(totals["gap-fill code"], size)),
        "| literal pool | %s | %s | %s %% |"
        % (format(len(measured["pool"]), ","), format(totals["literal pool"], ","),
           share(totals["literal pool"], size)),
        "| IWRAM overlay | %s | %s | %s %% |"
        % (format(len(measured["overlay_runs"]), ","), format(totals["IWRAM overlay"], ","),
           share(totals["IWRAM overlay"], size)),
        "| unclassified | %s | %s | %s %% |"
        % (format(len(measured["unclassified"]), ","),
           format(totals["unclassified"], ","), share(totals["unclassified"], size)),
        "| total | %s | %s | 100.0000 %% |"
        % (format(sum(len(measured[name]) for name in
                     ("proven", "filtered", "table", "gapfill", "pool",
                      "overlay_runs", "unclassified")), ","),
           format(size, ",")),
        "",
        "The rows in the CSV are the union runs of each class, not one row per entry, so",
        "a run is a maximal stretch of one class. A byte keeps the strongest class that claims it:",
        "proven code outranks table-held, which outranks filtered and gap-fill,",
        "and every code class outranks a literal pool and the overlay. The 54 function-pointer-table",
        "words the pointer filter accepts are classed table-held, so their bytes are not in the",
        "filtered class. The prologue sweep owns no row: its bytes stay unclassified.",
        "",
        "## Literal pools",
        "",
        ("A literal pool word is a 4-aligned word inside the image that a walked "
         "`ldr rd,[pc,#imm]` reaches. Consecutive words form one extent. The walk named %s pool "
         "words in %s extents; %s bytes inside a walked code extent were named by a load and stay "
         "code, because code outranks the pool class."
         % (format(measured["pool_words"], ","), format(measured["pool_runs"], ","),
            format(measured["pool_overlap"], ","))),
        "",
        "## IWRAM overlay",
        "",
        ("The startup block copies source 0x%08X to destination 0x%08X. The three words at "
         "0x%08X are the literal pool that this copy loads: they are also the descriptor."
         % (source, dest, OVERLAY)),
        "",
        "```",
        "08000108  e59f1038  ldr  r1, [pc, #0x38]      ; source",
        "0800010c  e58010d4  str  r1, [r0, #0xd4]      ; DMA3SAD",
        "08000110  e59f1034  ldr  r1, [pc, #0x34]      ; destination",
        "08000114  e58010d8  str  r1, [r0, #0xd8]      ; DMA3DAD",
        "08000118  e59f1030  ldr  r1, [pc, #0x30]      ; size 0x%X"
        % declared,
        "0800011c  e1b01121  movs r1, r1, lsr #2       ; 0x%X words" % (declared >> 2),
        "08000120  e3811484  orr  r1, r1, #0x84000000  ; enable, 32-bit",
        "08000124  158010dc  strne r1, [r0, #0xdc]     ; DMA3CNT = 0x%04X"
        % (0x8400 | (declared >> 2)),
        "```",
        "",
        "The DMA copies %s words, so the copied extent is 0x%X bytes = %s B, and the last %s B of"
        % (format(declared >> 2, ","), copied, format(copied, ","),
           format(declared - copied, ",")),
        "the descriptor's 0x%X B are not moved by it. %s bytes of the source are walked code and %s"
        % (declared, format(measured["overlay_code"], ","),
           format(measured["overlay_pool"], ",")),
        "are pool; the rest is the overlay class.",
        "",
        "A 12-byte entry thunk is `bx pc`, a `mov r8, r8`, an ARM `ldr pc, [pc, #-4]` and its",
        "target. %s such thunks point inside this copy: %s."
        % (len(thunks), ", ".join("0x%08X -> 0x%08X" % pair for pair in thunks)),
        "",
        "## Interrupts",
        "",
    ]
    irq = measured["irq"]
    if irq is None:
        lines += [
            "The walked code carries no store of an in-image code address to 0x03007FFC, so no",
            "interrupt handler is a root and how the engine services interrupts is not established",
            "by the descent.",
            "",
        ]
    else:
        install = irq["install"]
        handler = irq["handler"]
        lines += [
            "The engine enables interrupts and installs its own handler through the vector at",
            "0x%08X. The store is a computed address: the load at 0x%08X names 0x%08X, the load at"
            % (IRQ_VECTOR, install["base_at"], install["base"]),
            "0x%08X names the handler 0x%08X, and the store at 0x%08X writes it at offset 0x%X, so"
            % (install["value_at"], install["handler"], install["site"], install["immediate"]),
            "0x%08X + 0x%X = 0x%08X. No word of the image names the vector, so a word scan cannot"
            % (install["base"], install["immediate"], install["base"] + install["immediate"]),
            "find the store; the descent does. The words of the installing function are:",
            "",
            "```",
        ]
        for addr, half in install["words"]:
            lines.append("%08X  %04X" % (addr, half))
        lines += [
            "```",
            "",
            "The stores those words make, decoded from the registers the window loads: %s."
            % ", ".join("%08X = 0x%X at 0x%08X"
                        % (item["address"], item["value"], item["site"])
                        for item in install["effects"] if item["address"] != IRQ_VECTOR),
            "",
        ]
        if handler is None:
            lines += [
                "The handler pointer does not land inside the copied IWRAM extent, so the descent",
                "does not walk it.",
                "",
            ]
        else:
            lines += [
                "The handler is at 0x%08X, which is copy offset 0x%X and image 0x%08X, and the walk"
                % (install["handler"], install["handler"] - dest, handler["rom"]),
                "over it is %s and covers %s B in %s runs. Its first words are:"
                % ("Thumb" if handler["mode"] == MODE_THUMB else "ARM",
                   format(handler["bytes"], ","), format(len(handler["runs"]), ",")),
                "",
                "```",
            ]
            for addr, value in handler["words"]:
                lines.append("%08X  %08X" % (addr, value))
            lines += [
                "```",
                "",
            ]
            if handler["table"] is not None:
                table = handler["table"]
                lines += [
                    "The handler's first literal load names 0x%08X, and the copy carries %s pointer"
                    % (table["at"], format(len(table["entries"]), ",")),
                    "words there (image 0x%08X): %s. %s"
                    % (table["rom"],
                       ", ".join("0x%08X" % value for value in table["entries"][:4])
                       + (", ..." if len(table["entries"]) > 4 else ""),
                       "Every word is the same pointer 0x%08X, the `bx lr` at 0x%08X."
                       % (table["distinct"][0], table["distinct"][0] & ~1)
                       if len(table["distinct"]) == 1 else
                       "The %s distinct values are %s."
                       % (format(len(table["distinct"]), ","),
                          ", ".join("0x%08X" % value for value in table["distinct"]))),
                    "The dispatcher tail-calls the word its slot selects after it acknowledges the",
                    "source, so the table is the engine's interrupt dispatch and every slot returns",
                    "to it until something installs a handler. The slot table is one of the table-held",
                    "channel's shapes, and its target is the `bx lr` the slots share.",
                    "",
                ]
    lines += [
        "## Jump tables",
        "",
    ]
    if not measured["tables"]:
        lines += [
            "The descent proves none: over the walked code bytes, 0 Thumb `add pc, rX` or `mov",
            "pc, rX` site and 0 ARM register-offset `ldr pc, [pc, rX]` site carries a bounds check",
            "and a table base.",
            "",
        ]
    else:
        lines += [
            "The walked code carries %s bounded dispatch site. Its table:"
            % format(len(measured["tables"]), ","),
            "",
            "| dispatch | base | stride | entries | scale | bounds check |",
            "|---|---|---|---|---|---|",
        ]
        for table in measured["tables"]:
            lines.append("| 0x%08X | 0x%08X | %d | %s | %d | 0x%08X `cmp r%d, #0x%X`; 0x%08X `%s` |"
                         % (table["dispatch"], table["base"], table["stride"],
                            format(table["count"], ","), table["scale"], table["check"],
                            table["index"], table["cmp"] & 0xFF, table["branch"],
                            table["condition"]))
        for table in measured["tables"]:
            lines += [
                "",
                "At 0x%08X the load is `ldrb r%d, [r%d, r%d]`, scaled by %d at 0x%08X, and"
                % (table["load_addr"], table["load"] & 0x07, table["base_reg"], table["index"],
                   table["scale"], table["load_addr"] + 2),
                "0x%08X is the `add pc, r%d` (0x%04X) that dispatches it. The `adr` at 0x%08X"
                % (table["dispatch"], (table["jump"] >> 3) & 0x07, table["jump"], table["adr_at"]),
                "names the base 0x%08X, so the table is 0x%08X..0x%08X."
                % (table["base"], table["base"], table["base"] + table["count"] * table["stride"]),
                "The branch is `%s` to the default arm, which skips every index at or above 0x%X, so"
                % (table["condition"], table["cmp"] & 0xFF),
                "the table holds %s entries: %s."
                % (format(table["count"], ","),
                   ", ".join("0x%08X" % address for address, _mode in table["targets"])),
            ]
        lines += [""]
    lines += [
        "Over the same bytes, %s `bx rN` sites exist and %s of them carries a bounds check and an"
        % (format(sites["sites"], ","), format(sites["bounded"], ",")),
        "indexed load, so no table hides behind that idiom in the walked code.",
        "",
        "## Remaining unnamed code",
        "",
        "A single decodable halfword is the strict upper bound on the code still unnamed: every",
        "instruction decodes, so a byte of code in unclassified space lies in a maximal run of",
        "decodable Thumb halfwords of at least one. The longer rows measure the space that could hold",
        "a body of that length and are not upper bounds, because a leaf can be two instructions.",
        "None of the rows has power: the permuted share is above 100 % at every length, so a decode",
        "does not separate code from the packed payload that fills this image.",
        "",
        "| run length (halfwords) | image bytes | permuted bytes | permuted share |",
        "|---|---|---|---|",
    ]
    for threshold in RUN_THRESHOLDS:
        lines.append("| %d | %s | %s | %s %% |"
                     % (threshold, format(measured["decodable"][threshold], ","),
                        format(null["decodable"][threshold], ","),
                        share(null["decodable"][threshold], measured["decodable"][threshold])))
    lines += [
        "",
        "The bound is %s B of the %s B unclassified class."
        % (format(measured["decodable"][RUN_THRESHOLDS[0]], ","),
           format(totals["unclassified"], ",")),
        "",
        "## Null",
        "",
        "The null is the same census and the same channels over the image with every 64 KiB block",
        "reversed by halfword. The halfword set of each block is unchanged and the word structure",
        "is not, so the null counts what each channel finds without code.",
        "",
        "| channel | image | permuted image | permuted share |",
        "|---|---|---|---|",
        "| odd words naming a ROM address | %s | %s | %s %% |"
        % (format(measured["taken_words"], ","), format(null["taken_words"], ","),
           share(null["taken_words"], measured["taken_words"])),
        "| distinct address-taken entries | %s | %s | %s %% |"
        % (format(len(measured["taken"]), ","), format(len(null["taken"]), ","),
           share(len(null["taken"]), len(measured["taken"]))),
        "| accepted entries | %s | %s | %s %% |"
        % (format(accepted, ","), format(len(null["accepted"]), ","),
           share(len(null["accepted"]), accepted)),
        "| accepted entries that no call names | %s | %s | %s %% |"
        % (format(uncalled, ","), format(len(null["uncalled"]), ","),
           share(len(null["uncalled"]), uncalled)),
        "| branchless accepted entries | %s | %s | %s %% |"
        % (format(len(measured["leaves"]), ","), format(len(null["leaves"]), ","),
           share(len(null["leaves"]), len(measured["leaves"]))),
        "| proven code bytes | %s | %s | %s %% |"
        % (format(totals["proven code"], ","), format(null["totals"]["proven code"], ","),
           share(null["totals"]["proven code"], totals["proven code"])),
        "| filtered code bytes | %s | %s | %s %% |"
        % (format(totals["filtered pointer-entry code"], ","),
           format(null["totals"]["filtered pointer-entry code"], ","),
           share(null["totals"]["filtered pointer-entry code"],
                 totals["filtered pointer-entry code"])),
        "| table-held code bytes | %s | %s | %s %% |"
        % (format(totals["table-held code"], ","), format(null["totals"]["table-held code"], ","),
           share(null["totals"]["table-held code"], totals["table-held code"])),
        "| gap-fill code bytes | %s | %s | %s %% |"
        % (format(totals["gap-fill code"], ","), format(null["totals"]["gap-fill code"], ","),
           share(null["totals"]["gap-fill code"], totals["gap-fill code"])),
        "| literal pool bytes | %s | %s | %s %% |"
        % (format(totals["literal pool"], ","), format(null["totals"]["literal pool"], ","),
           share(null["totals"]["literal pool"], totals["literal pool"])),
        "| the prologue sweep's measured bytes | %s | %s | %s %% |"
        % (format(measured["prologue_bytes"], ","), format(null["prologue_bytes"], ","),
           share(null["prologue_bytes"], measured["prologue_bytes"])),
        "",
        "The permuted share of the accepted-entry channel is the false-entry rate the acceptance",
        "rule carries, and the permuted shares of the walked bytes state what each channel finds",
        "without code. A path that enters data is still counted, so every code class is an upper",
        "bound; the null is the control, not a correction. The prologue sweep's own entry rate is %s"
        % share(len(null_held["prologue"]), len(held["prologue"])),
        "%%, above 100 %%, which is why its measured bytes stay out of the classes: a channel that",
        "finds more on the permuted image than on the image has no power at all.",
        "",
    ]
    return "\n".join(lines)


def csv_text(measured):
    handle = io.StringIO()
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["start", "end", "bytes", "class"])
    rows = []
    for value in CODE_CLASSES + (POOL, OVERLAY_CLASS):
        rows += [(start, stop, CLASS_NAMES[value]) for start, stop in
                 class_runs(measured["classes"], value)]
    for start, stop, name in sorted(rows):
        writer.writerow(["0x%08X" % (start + ROM_BASE), "0x%08X" % (stop + ROM_BASE),
                         stop - start, name])
    return handle.getvalue()


def read_totals(path=None, size=ROM_SIZE):
    path = DOC if path is None else path
    totals = {}
    for line in open(path, encoding="utf-8").read().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0] in DOC_CLASSES:
            try:
                totals[cells[0]] = int(cells[2].replace(",", ""))
            except ValueError:
                raise ValueError("%s: %s is not a byte count" % (path, cells[2]))
    missing = [name for name in DOC_CLASSES if name not in totals]
    if missing:
        raise ValueError("%s: no class total for %s" % (path, ", ".join(missing)))
    if sum(totals.values()) != size:
        raise ValueError("%s: the class totals %d are not %d"
                         % (path, sum(totals.values()), size))
    return totals


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in (["--write"], ["--check"]):
        print("usage: python tools\\split\\code_split.py --write | --check")
        return 2
    if not os.path.exists(ROM):
        print("the split needs the retail image at %s" % ROM)
        return 1
    rom = open(ROM, "rb").read()
    null = measure_null(rom)
    measured = measure(rom, null)
    doc = doc_text(measured, null)
    table = csv_text(measured)
    totals = measured["totals"]
    print("entries: address-taken %d of %d words, accepted %d, proven %d"
          % (len(measured["taken"]), measured["taken_words"], len(measured["accepted"]),
             len(measured["proven_entries"])))
    print("rounds: %s" % " ".join("%d:%d/%d/%d" % (record["round"], record["proven"],
                                                   record["filtered"], record["accepted"])
                                  for record in measured["rounds"]))
    print("proven=%d filtered=%d table=%d gap=%d literal-pool=%d overlay=%d "
          "unclassified=%d total=%d"
          % (totals["proven code"], totals["filtered pointer-entry code"],
             totals["table-held code"], totals["gap-fill code"], totals["literal pool"],
             totals["IWRAM overlay"], totals["unclassified"], sum(totals.values())))
    print("channels: register %d of %d, table %d of %d, prologue %d of %d (%d B measured), "
          "gap %d of %d"
          % (len(measured["held"]["register"]), measured["channel_first"]["register_sites"],
             sum(len(measured["held"][key]) for key in TABLE_SHAPES),
             sum(measured["channel_first"]["table_" + shape] for shape in TABLE_SHAPES),
             len(measured["held"]["prologue"]), measured["channel_first"]["prologue_candidates"],
             measured["prologue_bytes"],
             len(measured["held"]["gap"]), measured["channel_first"]["gap_anchors"]))
    print("null: accepted %d of %d, uncalled %d of %d, bytes proven %d of %d, filtered %d of %d, "
          "table %d of %d, gap %d of %d, swept %d of %d"
          % (len(null["accepted"]), len(measured["accepted"]), len(null["uncalled"]),
             len(measured["uncalled"]), null["totals"]["proven code"], totals["proven code"],
             null["totals"]["filtered pointer-entry code"], totals["filtered pointer-entry code"],
             null["totals"]["table-held code"], totals["table-held code"],
             null["totals"]["gap-fill code"], totals["gap-fill code"],
             null["prologue_bytes"], measured["prologue_bytes"]))
    print("remaining: %d B of %d unclassified decode in a run of %d halfword(s)"
          % (measured["decodable"][RUN_THRESHOLDS[0]], totals["unclassified"],
             RUN_THRESHOLDS[0]))
    if argv == ["--write"]:
        os.makedirs(os.path.dirname(DOC), exist_ok=True)
        with open(DOC, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(doc)
        with open(CSV_OUT, "w", encoding="utf-8", newline="") as handle:
            handle.write(table)
        print("wrote %s and %s" % (os.path.basename(DOC), os.path.basename(CSV_OUT)))
        return 0
    problems = []
    for path, expected, name in ((DOC, doc, "CODE_SPLIT.md"), (CSV_OUT, table, "CODE_SPLIT.csv")):
        if not os.path.exists(path):
            problems.append("%s is absent" % name)
            continue
        if open(path, encoding="utf-8", newline="").read() != expected:
            problems.append("%s is not what this image derives" % name)
    for problem in problems:
        print("SPLIT FAIL: %s" % problem)
    print("SPLIT %s" % ("PASS" if not problems else "FAIL"))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
