from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import testkit
import thumb_vm

HEAP = 0x0801F08C
SLOT = 0x0801FC9C
RECT_FROM_FIELDS = 0x0800793A
QUEUE = 0x08026528
INCLUDE_POINT = 0x08028030
OVERLAPS = 0x0802805C
ADD_CAPPED = 0x080265AC
OUTRANKS = 0x08027E74
LIST = 0x02000000
MAX_SCALED = 0x08006D70
LOAD_POINT = 0x0800791A
FILL_CELLS = 0x080063E0
HALF_FILL_REQUEST = 0x0801F43C
WORD_FILL_REQUEST = 0x0801F46A
HALF_FILL_SOURCE = 0x03003910
WORD_FILL_SOURCE = 0x03003914
HEAD = 0x030022B4
NODE = 0x02000008
COPY_CHUNKS = 0x0801F412
ENABLE_DMA_INTERRUPT = 0x08021980
DISABLE_DMA_INTERRUPT = 0x08021A08
DMA_CHANNEL = 0x030038A0
SAVED_IME = 0x030038AC
DMA3 = 0x040000D4


def image():
    return testkit.rom_bytes(os.path.join(ROOT, "baserom.gba"), size=0x800000)


def run(address, registers, memory, stubs=None):
    data = image()
    return thumb_vm.run_function(data, address, registers=registers, memory=memory,
                                 body=thumb_vm.body_of(data, address), stubs=stubs)


def heap(size_words):
    memory = thumb_vm.Memory(image())
    memory.word(HEAD, NODE)
    memory.half(NODE + 2, size_words)
    memory.writes.clear()
    return memory


def writes_between(result, low, high):
    return [entry for entry in result["written"] if low <= entry[0] < high]


def test_heap_alloc_returns_distinct_non_overlapping_blocks_and_shrinks_the_free_list():
    memory = heap(0x40)
    first = run(HEAP, {0: 0x10}, memory)
    assert first["registers"][0] == 0x02000100
    assert first["calls"] == []
    assert memory.read(NODE + 2, 2) == 0x3A
    assert memory.read(NODE, 2) == 0x3E
    assert memory.read(0x020000F8 + 2, 2) == 4
    assert memory.read(0x020000F8 + 4, 2) == 2
    assert memory.read(0x020000F8 + 6, 1) == 1
    second = run(HEAP, {0: 0x10}, memory)
    assert second["registers"][0] == 0x020000E8
    assert memory.read(NODE + 2, 2) == 0x34
    assert memory.read(NODE, 2) == 0x38
    first_block = range(first["registers"][0], first["registers"][0] + 0x10)
    second_block = range(second["registers"][0], second["registers"][0] + 0x10)
    assert not set(first_block) & set(second_block)


def test_heap_alloc_returns_the_node_body_and_records_the_free_splice_for_an_exact_fit():
    memory = heap(4)
    result = run(HEAP, {0: 0x10}, memory)
    assert result["registers"][0] == NODE + 8
    assert result["calls"] == [(0x0801F0AA, 0x0801EFBC)]
    assert writes_between(result, 0x02000000, 0x02000400) == []


def test_slot_claim_takes_the_first_free_slot_and_initialises_its_fields():
    memory = thumb_vm.Memory(image())
    memory.blob(0x02000010, b"\x01")
    memory.writes.clear()
    result = run(SLOT, {0: 0x02000000, 1: 0x11111111, 2: 0x22, 3: 0x33}, memory)
    assert result["registers"][0] == 0x02000040
    assert writes_between(result, 0x02000000, 0x02001000) == [
        (0x02000068, 4, 0x11111111), (0x02000070, 4, 0x4000),
        (0x02000052, 1, 0x22), (0x02000053, 1, 0x33),
        (0x02000050, 1, 0x1F)]
    assert memory.read(0x02000010, 1) == 1


def test_slot_claim_returns_zero_when_every_slot_is_busy():
    memory = thumb_vm.Memory(image())
    for index in range(16):
        memory.blob(0x02000000 + 0x40 * index + 0x10, b"\x01")
    memory.writes.clear()
    result = run(SLOT, {0: 0x02000000, 1: 0x11111111, 2: 0x22, 3: 0x33}, memory)
    assert result["registers"][0] == 0
    assert writes_between(result, 0x02000000, 0x02001000) == []


def test_rect_from_fields_builds_the_rectangle_from_the_structure_words_and_bytes():
    memory = thumb_vm.Memory(image())
    memory.word(0x03000158, 0x00002000)
    memory.word(0x0300015C, 0x00003000)
    memory.blob(0x03000154, b"\x10\x20")
    result = run(RECT_FROM_FIELDS, {0: 0x02000200, 1: 0x03000000}, memory)
    assert result["registers"][0] == 0x02000210
    assert result["written"][-4:] == [(0x02000200, 4, 0x20), (0x02000204, 4, 0x30),
                                      (0x02000208, 4, 0x30), (0x0200020C, 4, 0x50)]
    memory.word(0x03000158, 0xFFFFF800)
    negative = run(RECT_FROM_FIELDS, {0: 0x02000200, 1: 0x03000000}, memory)
    assert negative["written"][-4:] == [(0x02000200, 4, 0xFFFFFFF8), (0x02000204, 4, 0x30),
                                        (0x02000208, 4, 0x8), (0x0200020C, 4, 0x50)]


def test_rect_include_point_grows_the_rectangle_to_cover_the_point():
    memory = thumb_vm.Memory(image())
    for index, value in enumerate([10, 20, 30, 40]):
        memory.word(0x02000000 + 4 * index, value)
    memory.word(0x02000010, 5)
    memory.word(0x02000014, 50)
    memory.writes.clear()
    result = run(INCLUDE_POINT, {0: 0x02000000, 1: 0x02000010}, memory)
    assert memory.read(0x02000000, 4) == 5
    assert memory.read(0x02000004, 4) == 20
    assert memory.read(0x02000008, 4) == 30
    assert memory.read(0x0200000C, 4) == 50
    assert result["written"] == [(0x02000000, 4, 5), (0x0200000C, 4, 0x32)]


def test_rect_overlaps_reports_whether_two_rectangles_intersect():
    memory = thumb_vm.Memory(image())
    for index, value in enumerate([10, 20, 30, 40]):
        memory.word(0x02000000 + 4 * index, value)
    for index, value in enumerate([20, 30, 50, 60]):
        memory.word(0x02000010 + 4 * index, value)
    for index, value in enumerate([40, 20, 50, 60]):
        memory.word(0x02000020 + 4 * index, value)
    inside = run(OVERLAPS, {0: 0x02000000, 1: 0x02000010}, memory)
    beside = run(OVERLAPS, {0: 0x02000000, 1: 0x02000020}, memory)
    assert inside["registers"][0] == 1
    assert beside["registers"][0] == 0


def test_queue_remove_shifts_the_following_entries_down_through_dma3():
    memory = thumb_vm.Memory(image())
    memory.word(0x02000000, 4)
    for index in range(4):
        memory.word(0x02000004 + 4 * index, 0x100 + index)
    memory.writes.clear()
    result = run(QUEUE, {0: 0x02000000, 1: 1}, memory)
    assert memory.read(0x02000000, 4) == 3
    assert result["written"] == [(0x02000000, 4, 3), (0x040000D4, 4, 0x0200000C),
                                 (0x040000D8, 4, 0x02000008), (0x040000DC, 2, 2),
                                 (0x040000DE, 2, 0x8400)]


def test_queue_remove_of_the_last_entry_writes_the_count_and_no_dma_register():
    memory = thumb_vm.Memory(image())
    memory.word(0x02000000, 4)
    for index in range(4):
        memory.word(0x02000004 + 4 * index, 0x100 + index)
    memory.writes.clear()
    result = run(QUEUE, {0: 0x02000000, 1: 3}, memory)
    assert memory.read(0x02000000, 4) == 3
    assert result["written"] == [(0x02000000, 4, 3)]


def test_counter_add_capped_stores_the_sum_until_the_limit_is_reached():
    memory = thumb_vm.Memory(image())
    memory.half(0x02000000, 10)
    memory.half(0x02000002, 20)
    memory.writes.clear()
    lower = run(ADD_CAPPED, {0: 0x02000000, 1: 5}, memory)
    assert memory.read(0x02000000, 2) == 15
    assert lower["written"] == [(0x02000000, 2, 15)]
    memory.half(0x02000000, 18)
    memory.writes.clear()
    capped = run(ADD_CAPPED, {0: 0x02000000, 1: 5}, memory)
    assert memory.read(0x02000000, 2) == 20
    assert capped["written"] == [(0x02000000, 2, 20)]

def test_bitmap_fill_cells_sets_or_clears_one_bit_for_each_eight_pixel_cell():
    memory = thumb_vm.Memory(image())
    for index, value in enumerate([8, 16, 40, 40]):
        memory.word(0x02000100 + 4 * index, value)
    memory.blob(0x02000200, bytes(0x60))
    memory.writes.clear()
    set_cells = run(FILL_CELLS, {0: 0x02000100, 1: 0x02000200, 2: 1}, memory)
    assert memory.read(0x02000240, 4) == 0x1E
    assert memory.read(0x02000260, 4) == 0x1E
    assert memory.read(0x02000280, 4) == 0x1E
    assert memory.read(0x02000220, 4) == 0
    written = writes_between(set_cells, 0x02000200, 0x02000300)
    assert [entry[2] for entry in written] == [2, 6, 0xE, 0x1E] * 3
    assert [entry[0] for entry in written] == [0x02000240] * 4 + [0x02000260] * 4 \
        + [0x02000280] * 4
    memory.blob(0x02000200, b"\xff" * 0x60)
    memory.writes.clear()
    run(FILL_CELLS, {0: 0x02000100, 1: 0x02000200, 2: 0}, memory)
    assert memory.read(0x02000240, 4) == 0xFFFFFFE1
    for index, value in enumerate([-8, -8, 8, 8]):
        memory.word(0x02000100 + 4 * index, value)
    memory.blob(0x02000200, bytes(0x60))
    memory.writes.clear()
    run(FILL_CELLS, {0: 0x02000100, 1: 0x02000200, 2: 1}, memory)
    assert memory.read(0x02000200, 4) == 1

def test_record_outranks_by_a_higher_byte_then_a_lower_word():
    memory = thumb_vm.Memory(image())
    memory.word(0x02000100, 0x02000200)
    memory.word(0x02000110, 0x02000300)
    memory.blob(0x02000208, b"\x01")
    memory.blob(0x02000308, b"\x02")
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 0
    memory.blob(0x02000208, b"\x03")
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 1
    memory.blob(0x02000208, b"\x02")
    memory.word(0x02000204, 5)
    memory.word(0x02000304, 7)
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 1
    memory.word(0x02000204, 0xFFFFFFF9)
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 1
    memory.word(0x02000204, 9)
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 0
    memory.word(0x02000204, 7)
    assert run(OUTRANKS, {0: 0x02000100, 1: 0x02000110}, memory)["registers"][0] == 0

def test_list_max_scaled_returns_the_largest_halfword_of_the_chain_times_sixty_four():
    memory = thumb_vm.Memory(image())
    memory.word(LIST + 4, 0)
    memory.blob(LIST, b"\x00")
    memory.half(0x02000698, 3)
    memory.blob(0x0200069C, b"\x01")
    memory.half(0x020006A2, 5)
    memory.blob(0x020006A6, b"\xff")
    assert run(MAX_SCALED, {0: LIST}, memory)["registers"][0] == 0x140
    memory.half(0x020006A2, 0xFFFF)
    assert run(MAX_SCALED, {0: LIST}, memory)["registers"][0] == 0x3FFFC0
    memory.word(LIST + 4, 0x80)
    assert run(MAX_SCALED, {0: LIST}, memory)["registers"][0] == 0
    memory.word(LIST + 4, 0)
    memory.blob(LIST, b"\xff")
    assert run(MAX_SCALED, {0: LIST}, memory)["registers"][0] == 0


def test_a_halfword_fill_request_stores_the_halfword_it_copies_in_the_dma3_source_word():
    memory = thumb_vm.Memory(image())
    memory.writes.clear()
    result = run(HALF_FILL_REQUEST,
                 {0: 0x02000100, 1: 0x06001000, 2: 0x89ABCDEF, 3: 0x2000}, memory)
    assert writes_between(result, HALF_FILL_SOURCE, HALF_FILL_SOURCE + 2) == [
        (HALF_FILL_SOURCE, 2, 0xCDEF), (HALF_FILL_SOURCE, 2, 0xCDEF)]
    assert [entry for entry in result["written"] if 0x02000100 <= entry[0] < 0x02000110] == [
        (0x02000100, 4, HALF_FILL_SOURCE), (0x02000104, 4, 0x06001000),
        (0x02000108, 2, 0x800), (0x0200010A, 2, 0x8100),
        (0x02000100, 4, HALF_FILL_SOURCE), (0x02000104, 4, 0x06002000),
        (0x02000108, 2, 0x800), (0x0200010A, 2, 0x8100)]


def test_a_word_fill_request_stores_the_word_it_copies_in_the_dma3_source_word():
    memory = thumb_vm.Memory(image())
    memory.writes.clear()
    result = run(WORD_FILL_REQUEST,
                 {0: 0x02000100, 1: 0x06001000, 2: 0x89ABCDEF, 3: 0x2000}, memory)
    assert writes_between(result, WORD_FILL_SOURCE, WORD_FILL_SOURCE + 4) == [
        (WORD_FILL_SOURCE, 4, 0x89ABCDEF), (WORD_FILL_SOURCE, 4, 0x89ABCDEF)]
    assert [entry for entry in result["written"] if 0x02000100 <= entry[0] < 0x02000110] == [
        (0x02000100, 4, WORD_FILL_SOURCE), (0x02000104, 4, 0x06001000),
        (0x02000108, 2, 0x400), (0x0200010A, 2, 0x8500),
        (0x02000100, 4, WORD_FILL_SOURCE), (0x02000104, 4, 0x06002000),
        (0x02000108, 2, 0x400), (0x0200010A, 2, 0x8500)]


def test_point_load_scaled_writes_the_two_global_words_shifted_into_the_structure():
    memory = thumb_vm.Memory(image())
    memory.word(0x03000158, 0x00002000)
    memory.word(0x0300015C, 0x00003000)
    memory.writes.clear()
    result = run(LOAD_POINT, {0: 0x02000100, 1: 0x03000000}, memory)
    assert writes_between(result, 0x02000100, 0x02000110) == [
        (0x02000100, 4, 0x20), (0x02000104, 4, 0x30)]
    memory.word(0x03000158, 0xFFFFF800)
    memory.writes.clear()
    result = run(LOAD_POINT, {0: 0x02000100, 1: 0x03000000}, memory)
    assert writes_between(result, 0x02000100, 0x02000110)[0] == (0x02000100, 4, 0xFFFFFFF8)

def test_dma3_copy_chunks_splits_a_copy_at_four_thousand_ninety_six_bytes_into_requests():
    memory = thumb_vm.Memory(image())
    memory.writes.clear()
    result = run(COPY_CHUNKS, {0: DMA3, 1: 0x06000000, 2: 0x02000000, 3: 0x1800}, memory)
    assert writes_between(result, DMA3, DMA3 + 0x10) == [
        (DMA3, 4, 0x02000000), (DMA3 + 4, 4, 0x06000000),
        (DMA3 + 8, 2, 0x400), (DMA3 + 0xA, 2, 0x8400),
        (DMA3, 4, 0x02001000), (DMA3 + 4, 4, 0x06001000),
        (DMA3 + 8, 2, 0x200), (DMA3 + 0xA, 2, 0x8400)]


def test_the_dma_interrupt_enable_saves_the_master_enable_and_raises_the_channel_bit():
    memory = thumb_vm.Memory(image())
    memory.half(0x04000208, 1)
    memory.half(0x04000200, 0)
    memory.half(0x04000202, 0)
    memory.blob(DMA_CHANNEL, b"\x02")
    memory.word(0x030038A8, 0x02000100)
    memory.half(0x02000000, 0x1234)
    memory.half(0x02000002, 0x5678)
    memory.half(0x02000004, 0x9ABC)
    memory.writes.clear()
    result = run(ENABLE_DMA_INTERRUPT, {0: 0x02000000}, memory)
    assert result["calls"] == []
    assert memory.read(SAVED_IME, 2) == 1
    assert memory.read(0x04000208, 2) == 1
    assert memory.read(0x04000200, 2) == 0x20
    assert memory.read(0x04000202, 2) == 0x20
    assert memory.read(0x030038A2, 2) == 0x1234
    assert memory.read(0x02000100, 2) == 0x5678
    assert memory.read(0x02000102, 2) == 0x9ABC
    assert memory.read(0x030038A8, 4) == 0x02000100


def test_the_dma_interrupt_disable_clears_the_channel_bit_and_restores_the_master_enable():
    memory = thumb_vm.Memory(image())
    memory.half(SAVED_IME, 1)
    memory.half(0x04000208, 0)
    memory.half(0x04000200, 0x20)
    memory.blob(DMA_CHANNEL, b"\x02")
    memory.word(0x030038A8, 0x02000100)
    memory.writes.clear()
    run(DISABLE_DMA_INTERRUPT, {}, memory)
    assert memory.read(0x04000200, 2) == 0
    assert memory.read(0x04000208, 2) == 1
    assert memory.read(0x02000100, 4) == 0


CASES = [
    {"address": 0x0801F2F4, "name": "Handler_RunScoped", "registers": {0: 0x02000100},
     "memory": [(0x03000E1C, 4, 0xAAAAAAAA), (0x03000E24, 4, 0),
                (0x02000100, 4, 0x02000200)],
     "return": 0x02000100,
     "writes": [(0x03000E24, 4, 1), (0x03000E28, 4, 0xAAAAAAAA),
                (0x03000E1C, 4, 0x030022B8), (0x03000E1C, 4, 0x02000100),
                (0x03000E1C, 4, 0x030022B8), (0x03000E24, 4, 0),
                (0x03000E1C, 4, 0xAAAAAAAA)],
     "calls": [(0x0801F314, 0x08021D2A), (0x0801F31A, 0x0801F294),
               (0x0801F330, 0x08021D2A)]},
    {"address": 0x08009370, "name": "Sprite_Select", "registers": {0: 7},
     "stubs": {0x08009324: {0: 0x1234}, 0x08006E0A: {0: 1}},
     "calls": [(0x08009380, 0x08009324), (0x0800938C, 0x08006E0A)]},
    {"address": 0x08009370, "name": "Sprite_Select", "registers": {0: 0},
     "memory": [(0x03001FA8, 4, 0x02000500)], "return": 0x02000500, "calls": []},
    {"address": 0x08020E5C, "name": "Surface_New", "registers": {0: 0x02000100, 1: 8, 2: 6},
     "stubs": {0x0801F58C: {}, 0x0801F08C: {0: 0x02000200}},
     "return": 0x02000100,
     "writes": [(0x0200012C, 4, 8), (0x02000130, 4, 6), (0x02000134, 4, 0x30),
                (0x02000124, 4, 0x02000200), (0x02000120, 4, 0x08020D91),
                (0x02000129, 1, 0)],
     "calls": [(0x08020E8A, 0x0801F58C), (0x08020E98, 0x0801F08C)]},
    {"address": 0x0802141C, "name": "Random_Scale", "registers": {0: 0x100},
     "stubs": {0x080213FC: {0: 0x8000}}, "return": 0x80,
     "calls": [(0x08021420, 0x080213FC)]},
    {"address": 0x0801F110, "name": "Heap_Free", "registers": {0: 0x02000008},
     "memory": [(0x02000000, 2, 0), (0x02000004, 2, 0)],
     "writes": [(0x02000006, 1, 0), (0x030022B4, 4, 0x02000000),
                (0x02000008, 2, 0), (0x0200000A, 2, 0)], "calls": []},
    {"address": 0x0801F636, "name": "Text_DrawLine",
     "registers": {0: 0x02000000, 1: 0x02000200},
     "memory": [(0x02000000, 1, 0), (0x02000001, 1, 6), (0x02000004, 4, 0x100),
                (0x02000008, 4, 0x40), (0x0200000C, 4, 0x02000100),
                (0x02000200, b"AB\x00"), (0x02000182, 2, 1), (0x02000184, 2, 1),
                (0x02000102, 2, 5)],
     "return": 0, "writes": [(0x02000004, 4, 0x10C)],
     "calls": [(0x0801F6B8, 0x08021D2E), (0x0801F6B8, 0x08021D2E)]},
    {"address": 0x0800E04C, "name": "Queue_Append",
     "registers": {0: 0x02000100, 1: 0x02000200, 2: 0x02000000},
     "memory": [(0x02000100, 4, 1), (0x02000150, 4, 0x02000300), (0x02000304, 4, 0)],
     "return": 1, "writes": [(0x02000304, 4, 0x02000200)], "calls": []},
    {"address": 0x080068CA, "name": "List_RemoveValue",
     "registers": {0: 0x02000000, 1: 0x02000200},
     "memory": [(0x02000004, 4, 2), (0x02000008, 4, 0x1111),
                (0x0200000C, 4, 0x02000200), (0x0200040C, 4, 0),
                (0x02000200, 4, 0x02000210)],
     "return": 0x02000200, "writes": [(0x02000010, 4, 0x03001F20)],
     "calls": [(0x080068F6, 0x08026528), (0x0800693C, 0x08021D2A)]},
    {"address": 0x08006DA6, "name": "List_Dispatch",
     "registers": {0: 0x02000000, 1: 0x11, 2: 6},
     "memory": [(0x02000004, 4, 1), (0x02000008, 4, 0x02000300),
                (0x02000300, 4, 0x02000400), (0x0200040C, 4, 0)],
     "stubs": {0x08021D2E: {0: 0}},
     "return": 0, "writes": [], "calls": [(0x08006DD0, 0x08021D2E)]},
    {"address": 0x08020EAA, "name": "Surface_Free", "registers": {0: 0x02000100, 1: 1},
     "memory": [(0x02000124, 4, 0x02000200)],
     "calls": [(0x08020EB2, 0x0801F110), (0x08020EBC, 0x0801F110)]},
    {"address": 0x080079B8, "name": "Rect_FromDefinition",
     "registers": {0: 0x02000000, 1: 0x02000100},
     "memory": [(0x02000110, 1, 0), (0x02000148, 4, 0x02000300),
                (0x02000258, 4, 0x1000), (0x0200025C, 4, 0x2000),
                (0x0200030C, 4, 0x10), (0x02000310, 4, 0x20),
                (0x02000314, 4, 0x30), (0x02000318, 4, 0x40)],
     "writes": [(0x02000000, 4, 0x20), (0x02000004, 4, 0x40),
                (0x02000008, 4, 0x40), (0x0200000C, 4, 0x60)], "calls": []},
    {"address": 0x08004FF8, "name": "Sprite_InitFromDefinition",
     "registers": {0: 0x02000100, 1: 0x02000200},
     "memory": [(0x02000204, 4, 0x1234), (0x02000208, 4, 0xAAAA),
                (0x0200020C, 4, 0xBBBB)],
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 0x08025FE0), (0x02000108, 4, 0xBBBB),
                (0x02000104, 4, 0xAAAA), (0x0200010C, 4, 0x1234)],
     "calls": [(0x0800500A, 0x08021D28)]},
    {"address": 0x0800763C, "name": "Object_SwitchState",
     "registers": {0: 0x02000100, 1: 0x02000200},
     "memory": [(0x02000118, 4, 0x02000300), (0x02000300, 4, 0x02000310),
                (0x02000200, 4, 0x02000320)],
     "writes": [(0x02000118, 4, 0x02000200)],
     "calls": [(0x0800764C, 0x08021D2C), (0x0800765C, 0x08021D2C)]},
    {"address": 0x08006E0A, "name": "List_FirstMatch", "registers": {0: 0x02000000, 1: 5, 2: 6},
     "memory": [(0x02000004, 4, 1), (0x02000008, 4, 0x02000300),
                (0x02000300, 4, 0x02000310), (0x0200040C, 4, 0)],
     "stubs": {0x08021D2E: {0: 1}}, "return": 1,
     "calls": [(0x08006E2E, 0x08021D2E)]},
    {"address": 0x08006E0A, "name": "List_FirstMatch", "registers": {0: 0x02000000, 1: 5, 2: 6},
     "memory": [(0x02000004, 4, 0), (0x0200040C, 4, 0)],
     "stubs": {0x08021D2E: {0: 0}}, "return": 0, "calls": []},
    {"address": 0x08005D6C, "name": "Bitmap_AllCellsSet",
     "registers": {0: 0x02000000, 1: 0x02000100},
     "memory": [(0x02000000, 4, 0), (0x02000004, 4, 0), (0x02000008, 4, 8),
                (0x0200000C, 4, 8), (0x02000100, 4, 1)],
     "return": 1, "calls": []},
    {"address": 0x08005D6C, "name": "Bitmap_AllCellsSet",
     "registers": {0: 0x02000000, 1: 0x02000100},
     "memory": [(0x02000000, 4, 0), (0x02000004, 4, 0), (0x02000008, 4, 8),
                (0x0200000C, 4, 8), (0x02000100, 4, 0)],
     "return": 0, "calls": []},
]


CASES_TWO = [
    {"address": 0x0801F2CE, "name": "Handler_Restore", "registers": {0: 0x02000100},
     "memory": [(0x03000E1C, 4, 0x02000300), (0x02000300, 4, 0x02000400),
                (0x02000100, 4, 0x02000200)],
     "return": 0x02000100,
     "writes": [(0x03000E1C, 4, 0x030022B8), (0x03000E1C, 4, 0x02000100)],
     "calls": [(0x0801F2E0, 0x08021D2A), (0x0801F2EC, 0x08021D2A)]},
    {"address": 0x0801FEE8, "name": "Fade_Decrease", "registers": {0: 0x02000000},
     "memory": [(0x02000048, 1, 10), (0x0200004B, 1, 3)],
     "writes": [(0x02000048, 1, 7), (0x02000012, 1, 7), (0x02000010, 1, 0x10)],
     "calls": []},
    {"address": 0x0801FEE8, "name": "Fade_Decrease", "registers": {0: 0x02000000},
     "memory": [(0x02000048, 1, 2), (0x0200004B, 1, 5), (0x0200004A, 1, 0xFF)],
     "writes": [(0x02000048, 1, 0xFD), (0x02000048, 1, 0), (0x0200004A, 1, 0xFC),
                (0x02000012, 1, 0), (0x02000010, 1, 0x10)], "calls": []},
    {"address": 0x0801FF16, "name": "Fade_Increase", "registers": {0: 0x02000000},
     "memory": [(0x02000048, 1, 0x3C), (0x0200004B, 1, 1)],
     "writes": [(0x02000048, 1, 0x3D), (0x02000012, 1, 0x3D), (0x02000010, 1, 0x10)],
     "calls": []},
    {"address": 0x0801FF16, "name": "Fade_Increase", "registers": {0: 0x02000000},
     "memory": [(0x02000048, 1, 0x3C), (0x0200004B, 1, 5), (0x0200004A, 1, 0xFF)],
     "writes": [(0x02000048, 1, 0x41), (0x02000048, 1, 0x40), (0x0200004A, 1, 0xFC),
                (0x02000012, 1, 0x40), (0x02000010, 1, 0x10)], "calls": []},
    {"address": 0x0802142E, "name": "Random_Below", "registers": {0: 6},
     "stubs": {0x080213FC: {0: 5}}, "return": 1,
     "calls": [(0x08021432, 0x080213FC)]},
    {"address": 0x0802142E, "name": "Random_Below", "registers": {0: 5},
     "stubs": {0x080213FC: {0: 5}}, "return": 0,
     "calls": [(0x08021432, 0x080213FC)]},
    {"address": 0x080213FC, "name": "Random_Next", "registers": {},
     "memory": [(0x03003890, 4, 0), (0x03003894, 4, 0)],
     "return": 0xFDD257F3,
     "writes": [(0x03003894, 4, 0x04F9647E), (0x03003890, 4, 0x02CBBC71)],
     "calls": []},
    {"address": 0x08026414, "name": "Rect_Midpoint",
     "registers": {0: 0x02000000, 1: 0x02000100},
     "memory": [(0x02000100, 4, 10), (0x02000104, 4, 20), (0x02000108, 4, 30),
                (0x0200010C, 4, 40)],
     "writes": [(0x02000004, 4, 0x1E), (0x02000000, 4, 0x14)], "calls": []},
    {"address": 0x0802664C, "name": "Palette_New", "registers": {0: 0x02000100, 1: 7},
     "stubs": {0x0800DA68: {}}, "return": 0x02000100,
     "writes": [(0x02000100, 4, 0x08024F94), (0x02000504, 4, 0),
                (0x02000508, 4, 7)],
     "calls": [(0x08026666, 0x0800DA68)]},
    {"address": 0x08002BF2, "name": "Object_SetFields",
     "registers": {0: 0x02000100, 1: 1, 2: 2, 3: 3},
     "memory": [(0x03007F00, 4, 0x4444)], "return": 0x02000114,
     "writes": [(0x02000104, 4, 1), (0x02000108, 4, 2), (0x0200010C, 4, 3),
                (0x02000110, 4, 0x4444)], "calls": []},
    {"address": 0x08001A26, "name": "Entry_RunIfEnabled",
     "registers": {0: 0x02000000, 1: 1},
     "memory": [(0x02000165, 1, 2)], "return": 0, "calls": []},
    {"address": 0x08001A26, "name": "Entry_RunIfEnabled",
     "registers": {0: 0x02000000, 1: 1},
     "memory": [(0x02000165, 1, 3)], "stubs": {0x08003E00: {0: 9}}, "return": 9,
     "calls": [(0x08001A3E, 0x08003E00)]},
    {"address": 0x08004214, "name": "Table_IndexForValue",
     "registers": {0: 0x02000100}, "memory": [(0x02000110, 4, 0x15E6B71)],
     "return": 0x32, "calls": []},
    {"address": 0x08004214, "name": "Table_IndexForValue",
     "registers": {0: 0x02000100}, "memory": [(0x02000110, 4, 0)],
     "return": 1, "calls": []},
    {"address": 0x080076EE, "name": "Table_RemapBytes",
     "registers": {0: 0x02000000, 1: 0x02000200},
     "memory": [(0x0200002C, 4, 0x02000300), (0x02000200, bytes(range(256))),
                (0x02000300, bytes(255 - index for index in range(256)))],
     "writes_head": [(0x02000028, 4, 0x02000200), (0x02000024, 4, 0x02000050)],
     "writes_len": 259,
     "writes_tail": [(0x0200014F, 1, 0), (0x02000020, 4, 0)],
     "calls": []},
    {"address": 0x08003F06, "name": "Script_TestFlag", "registers": {0: 0x00010008},
     "memory": [(0x03000F45, 1, 1)], "return": 1, "calls": []},
    {"address": 0x08003F06, "name": "Script_TestFlag", "registers": {0: 0x00020008},
     "memory": [(0x03000F45, 1, 1)], "return": 0, "calls": []},
    {"address": 0x08003F06, "name": "Script_TestFlag", "registers": {0: 0x00030008},
     "memory": [(0x03000F45, 1, 1)], "return": 1,
     "writes": [(0x03000F45, 1, 0)], "calls": []},
    {"address": 0x08003F06, "name": "Script_TestFlag", "registers": {0: 0},
     "return": 1, "calls": []},
]


CASES_THREE = [
    {"address": 0x0800426A, "name": "Table_PreviousWord", "registers": {0: 2},
     "return": 0x32, "calls": []},
    {"address": 0x0800426A, "name": "Table_PreviousWord", "registers": {0: 3},
     "return": 0x96, "calls": []},
    {"address": 0x0801FD56, "name": "Slot_InitFields", "registers": {0: 0x02000000, 1: 0x5A},
     "writes_len": 32,
     "writes_head": [(0x02000034, 1, 0x5A), (0x02000010, 1, 0x10)],
     "writes_tail": [(0x020003F4, 1, 0x5A), (0x020003D0, 1, 0x10)],
     "reads": [(0x02000034, 1, 0x5A), (0x020003F4, 1, 0x5A)], "calls": []},
    {"address": 0x08020AC8, "name": "Slot_InitFieldsWide",
     "registers": {0: 0x02000000, 1: 0x5A},
     "writes_len": 30,
     "writes_head": [(0x0200004C, 1, 0x5A), (0x02000028, 1, 0x10)],
     "writes_tail": [(0x0200058C, 1, 0x5A), (0x02000568, 1, 0x10)],
     "reads": [(0x0200004C, 1, 0x5A), (0x0200058C, 1, 0x5A)], "calls": []},
    {"address": 0x08013BF4, "name": "Rect_FromCentre", "registers": {0: 0x02000000},
     "memory": [(0x02000018, 4, 0x02000200), (0x02000200, bytes([1, 2, 3, 4])),
                (0x02000020, 4, 0x800), (0x02000024, 4, 0x1000)],
     "writes": [(0x02000028, 4, 7), (0x0200002C, 4, 0xE), (0x02000034, 4, 0x12),
                (0x02000030, 4, 0xA), (0x02000004, 4, 0x12)], "calls": []},
    {"address": 0x080211C8, "name": "Bitmap_BlitRows",
     "registers": {0: 0x02000000, 1: 0x02000300, 2: 0x02000200},
     "memory": [(0x0200002C, 4, 4), (0x02000024, 4, 0x02000100),
                (0x02000200, 4, 0), (0x02000204, 4, 0), (0x02000208, 4, 3),
                (0x0200020C, 4, 2), (0x02000300, b"ABCDEF")],
     "writes": [(0x02000100, 1, 0x41), (0x02000101, 1, 0x42), (0x02000102, 1, 0x43),
                (0x02000104, 1, 0x44), (0x02000105, 1, 0x45), (0x02000106, 1, 0x46)],
     "calls": []},
    {"address": 0x0801F7FC, "name": "Text_MeasureLine",
     "registers": {0: 0x02000000, 1: 0x02000200, 2: 100, 3: 0x02000300},
     "memory": [(0x0200000C, 4, 0x02000100), (0x02000200, b"AA\x00"),
                (0x02000182, 2, 1), (0x02000184, 2, 1), (0x02000102, 2, 5)],
     "reads": [(0x02000300, 4, 0x02000200), (0x02000304, 4, 0x02000202),
               (0x02000308, 4, 12), (0x0200030C, 4, 1)], "calls": []},
    {"address": 0x08003C24, "name": "Scene_Clear", "registers": {0: 0x02000000},
     "low": 0x02000000, "high": 0x04000100, "skip": (0x03007000, 0x03008000),
     "writes": [(0x02000001, 1, 0), (0x02000008, 4, 0), (0x02000000, 1, 3),
                (0x040000D4, 4, 0x081D9548), (0x040000D8, 4, 0x0200000C),
                (0x040000DC, 2, 0x2A), (0x040000DE, 2, 0x8400),
                (0x03003910, 2, 0), (0x040000D4, 4, 0x03003910),
                (0x040000D8, 4, 0x020000B4), (0x040000DC, 2, 0x19),
                (0x040000DE, 2, 0x8100),
                (0x03003910, 2, 0), (0x040000D4, 4, 0x03003910),
                (0x040000D8, 4, 0x0200012B), (0x040000DC, 2, 0x19),
                (0x040000DE, 2, 0x8100)], "calls": []},
]


CASES_FOUR = [
    {"address": 0x0800D138, "name": "List_NewNode", "registers": {0: 0, 1: 0x1234},
     "stubs": {0x0801F08C: {0: 0x02000100}}, "return": 0x02000100,
     "writes": [(0x02000104, 1, 0xFF), (0x02000100, 4, 0), (0x02000108, 4, 0x1234)],
     "calls": [(0x0800D142, 0x0801F08C)]},
    {"address": 0x0800D138, "name": "List_NewNode", "registers": {0: 0x02000200, 1: 7},
     "return": 0x02000200,
     "writes": [(0x02000204, 1, 0xFF), (0x02000200, 4, 0), (0x02000208, 4, 7)],
     "calls": []},
    {"address": 0x0801F6D8, "name": "Text_DrawFormat",
     "registers": {0: 0x02000000, 1: 0x03000100}, "memory": [(0x03000100, b"AB\x00")],
     "stubs": {0x08021CF0: {0: 5}, 0x0801F636: {0: 1}}, "return": 1,
     "calls": [(0x0801F6EC, 0x08021CF0), (0x0801F6F4, 0x0801F636)]},
    {"address": 0x08007662, "name": "Object_SetChild",
     "registers": {0: 0x02000100, 1: 0x02000300},
     "memory": [(0x0200011C, 4, 0x02000200), (0x02000200, 4, 0x02000210),
                (0x02000300, 4, 0x02000310)],
     "stubs": {0x08021D2C: {}}, "return": 0x02000300,
     "writes": [(0x0200011C, 4, 0x02000300)],
     "calls": [(0x08007672, 0x08021D2C), (0x08007682, 0x08021D2C)]},
    {"address": 0x080076BC, "name": "Object_ResetChild", "registers": {0: 0x02000100},
     "memory": [(0x0200011C, 4, 0x02000200), (0x02000124, 4, 5), (0x0200012C, 4, 7),
                (0x02000200, 4, 0x02000210), (0x03001F3C, 4, 0x02000300)],
     "stubs": {0x08021D2C: {}},
     "writes": [(0x02000120, 4, 0), (0x02000124, 4, 7), (0x0200011C, 4, 0x03001F3C)],
     "calls": [(0x080076D8, 0x08021D2C), (0x080076E8, 0x08021D2C)]},
    {"address": 0x0801EFBC, "name": "Heap_Unlink", "registers": {0: 0x02000100},
     "memory": [(0x02000108, 2, 0), (0x0200010A, 2, 0)], "return": 0x02000100,
     "writes": [(0x02000106, 1, 1), (0x030022B4, 4, 0)], "calls": []},
    {"address": 0x0801EFBC, "name": "Heap_Unlink", "registers": {0: 0x02000100},
     "memory": [(0x02000108, 2, 4), (0x0200010A, 2, 0)], "return": 0,
     "writes": [(0x02000106, 1, 1), (0x030022B4, 4, 0x02000010), (0x0200001A, 2, 0)],
     "calls": []},
    {"address": 0x0801EFBC, "name": "Heap_Unlink", "registers": {0: 0x02000100},
     "memory": [(0x02000108, 2, 4), (0x0200010A, 2, 8)], "return": 8,
     "writes": [(0x02000106, 1, 1), (0x02000028, 2, 4), (0x0200001A, 2, 8)], "calls": []},
    {"address": 0x08002DC8, "name": "Object_SetStateTwo", "registers": {0: 0x02000100},
     "memory": [(0x02000100, 4, 0x02000300), (0x02000300, 4, 0x02000400)],
     "stubs": {0x08021D2A: {}}, "return": 0x02000100,
     "writes": [(0x02000108, 1, 2)], "calls": [(0x08002DD4, 0x08021D2A)]},
    {"address": 0x0802645C, "name": "Sprite_ObjectDirectory", "registers": {0: 0x02000100},
     "memory": [(0x02000108, 1, 2)], "stubs": {0x08009324: {0: 0x02000500}},
     "return": 0x02000500, "calls": [(0x0802646C, 0x08009324)]},
    {"address": 0x080201F8, "name": "Object_StepPhase", "registers": {0: 0x02000100},
     "memory": [(0x0200014F, 1, 0x10), (0x02000150, 1, 0x40), (0x02000151, 1, 0),
                (0x02000140, 4, 0x1000)],
     "return": 0x02000100,
     "writes": [(0x02000151, 1, 0x10), (0x02000130, 4, 0x800), (0x02000110, 1, 2)],
     "calls": []},
    {"address": 0x080201F8, "name": "Object_StepPhase", "registers": {0: 0x02000100},
     "memory": [(0x0200014F, 1, 0x10), (0x02000150, 1, 0x40), (0x02000151, 1, 0x30),
                (0x02000140, 4, 0x1000)],
     "return": 0x02000100,
     "writes": [(0x02000151, 1, 0), (0x02000130, 4, 0x1000), (0x02000110, 1, 2)],
     "calls": []},
    {"address": 0x08012EA4, "name": "TileBank_LoadDescriptor", "registers": {0: 0x02000100},
     "memory": [(0x02000144, 4, 0x02000200), (0x0200022C, 4, 0x02000300),
                (0x02000304, 4, 0x40), (0x0200010E, 2, 1)],
     "stubs": {0x0801F08C: {0: 0x02000400}, 0x0801F394: {}, 0x0801F412: {},
               0x0801F110: {}},
     "return": 0x02000400, "writes": [],
     "calls": [(0x08012EAE, 0x0801F08C), (0x08012EBA, 0x0801F394),
               (0x08012ED0, 0x0801F412), (0x08012ED6, 0x0801F110)]},
    {"address": 0x08006618, "name": "Table_UnlinkNode", "registers": {0: 0x02000100, 1: 2},
     "memory": [(0x020007B0, 1, 3), (0x020007B1, 1, 1)], "return": 0x020007AE,
     "writes": [(0x020007A6, 1, 3), (0x020007BB, 1, 1)], "calls": []},
    {"address": 0x08006618, "name": "Table_UnlinkNode", "registers": {0: 0x02000100, 1: 2},
     "memory": [(0x020007B0, 1, 3), (0x020007B1, 1, 0xFF)], "return": 0x020007AE,
     "writes": [(0x02000100, 1, 3), (0x020007BB, 1, 0xFF)], "calls": []},
    {"address": 0x08006618, "name": "Table_UnlinkNode", "registers": {0: 0x02000100, 1: 2},
     "memory": [(0x020007B0, 1, 0xFF), (0x020007B1, 1, 1)], "return": 0x02000100,
     "writes": [(0x020007A6, 1, 0xFF)], "calls": []},
    {"address": 0x08003C6E, "name": "Counter_StepRandom",
     "registers": {0: 0x02000100, 1: 3, 2: 0x02000200},
     "memory": [(0x02000100, 2, 0x10), (0x02000102, 2, 0x14), (0x02000200, 2, 0x100)],
     "stubs": {0x0802141C: {0: 2}}, "return": 0x132,
     "writes": [(0x02000200, 2, 0x132)], "calls": [(0x08003C80, 0x0802141C)]},
    {"address": 0x08003C6E, "name": "Counter_StepRandom",
     "registers": {0: 0x02000100, 1: 3, 2: 0x02000200},
     "memory": [(0x02000100, 2, 0x10), (0x02000102, 2, 0x14), (0x02000200, 2, 0x6400)],
     "stubs": {0x0802141C: {0: 2}}, "return": 0x6432,
     "writes": [(0x02000200, 2, 0x6432), (0x02000200, 2, 0x6400)],
     "calls": [(0x08003C80, 0x0802141C)]},
    {"address": 0x08021140, "name": "Bitmap_StampCells",
     "registers": {0: 0x02000000, 1: 0x02000200, 2: 0x02000100},
     "memory": [(0x02000024, 4, 0x02000300), (0x0200002C, 4, 8),
                (0x02000100, 4, 1), (0x02000104, 4, 0),
                (0x02000200, 2, 3), (0x02000202, 2, 2),
                (0x02000204, bytes([0, 7, 0, 9, 0, 8]))],
     "return": 0x02000000,
     "writes": [(0x02000302, 1, 7), (0x02000309, 1, 9), (0x0200030B, 1, 8)],
     "calls": []},
    {"address": 0x080075A8, "name": "Scene_InitFromDefinition",
     "registers": {0: 0x02000100, 1: 0x02000200, 2: 0x02000400},
     "memory": [(0x02000200, 2, 0x40), (0x02000208, 4, 0x1234),
                (0x02000400, 4, 0x02000600), (0x02000600, 4, 0x02000610)],
     "stubs": {0x080067AC: {0: 0x11}, 0x0801F08C: {0: 0x02000500}, 0x08021D2C: {}},
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 0x08023A1C), (0x0200010E, 2, 0x40),
                (0x0200010C, 2, 0x11), (0x02000100, 4, 0x0802489C),
                (0x02000148, 4, 0x02000200), (0x02000118, 4, 0x02000400),
                (0x0200011C, 4, 0x03001F3C), (0x02000120, 4, 0),
                (0x02000128, 4, 0), (0x02000124, 4, 0x1234),
                (0x0200012C, 4, 0x1234), (0x02000110, 1, 0),
                (0x02000130, 4, 0x02000500)],
     "calls": [(0x080075BC, 0x080067AC), (0x080075E0, 0x0801F08C),
               (0x080075F0, 0x08021D2C)]},
]


CASES_FIVE = [
    {"address": 0x0801EFF4, "name": "Heap_Link", "registers": {0: 0x02000100},
     "memory": [(0x030022B4, 4, 0x02000010)], "return": 0x02000100,
     "writes": [(0x02000108, 2, 4), (0x0200001A, 2, 0x40), (0x0200010A, 2, 0),
                (0x030022B4, 4, 0x02000100)], "calls": []},
    {"address": 0x0801EFF4, "name": "Heap_Link", "registers": {0: 0x02000100},
     "memory": [(0x030022B4, 4, 0)], "return": 0x02000100,
     "writes": [(0x02000108, 2, 0), (0x0200010A, 2, 0),
                (0x030022B4, 4, 0x02000100)], "calls": []},
    {"address": 0x080019F6, "name": "Entry_IsEnabled",
     "registers": {0: 0x02000000, 1: 2}, "memory": [(0x020002C9, 1, 0x01)],
     "return": 1, "calls": []},
    {"address": 0x080019F6, "name": "Entry_IsEnabled",
     "registers": {0: 0x02000000, 1: 2}, "memory": [(0x020002C9, 1, 0)],
     "return": 0, "calls": []},
    {"address": 0x08003E00, "name": "Entry_CountFlags", "registers": {0: 0x02000100},
     "memory": [(0x02000120, 4, 1), (0x0200013C, 4, 0), (0x02000158, 4, 3),
                (0x02000174, 4, 2), (0x02000190, 4, 5), (0x020001AC, 4, 4)],
     "return": 3, "calls": []},
    {"address": 0x08003E00, "name": "Entry_CountFlags", "registers": {0: 0x02000100},
     "memory": [(0x02000120, 4, 1), (0x0200013C, 4, 1), (0x02000158, 4, 1),
                (0x02000174, 4, 1), (0x02000190, 4, 1), (0x020001AC, 4, 1)],
     "return": 6, "calls": []},
    {"address": 0x08027FEC, "name": "Rect_Intersect",
     "registers": {0: 0x02000000, 1: 0x02000100, 2: 0x02000200},
     "memory": [(0x02000100, 4, 10), (0x02000104, 4, 20),
                (0x02000108, 4, 100), (0x0200010C, 4, 200),
                (0x02000200, 4, 15), (0x02000204, 4, 5),
                (0x02000208, 4, 90), (0x0200020C, 4, 250)],
     "writes": [(0x02000000, 4, 15), (0x02000004, 4, 20),
                (0x02000008, 4, 90), (0x0200000C, 4, 200)], "calls": []},
    {"address": 0x08027FEC, "name": "Rect_Intersect",
     "registers": {0: 0x02000000, 1: 0x02000100, 2: 0x02000200},
     "memory": [(0x02000100, 4, 10), (0x02000104, 4, 20),
                (0x02000108, 4, 100), (0x0200010C, 4, 200),
                (0x02000200, 4, -5), (0x02000204, 4, -6),
                (0x02000208, 4, 40), (0x0200020C, 4, 50)],
     "writes": [(0x02000000, 4, 10), (0x02000004, 4, 20),
                (0x02000008, 4, 40), (0x0200000C, 4, 50)], "calls": []},
    {"address": 0x08003E42, "name": "Bitmap_TestCell",
     "registers": {0: 0x02000100, 1: 10}, "memory": [(0x020001B5, 1, 4)],
     "return": 1, "calls": []},
    {"address": 0x08003E42, "name": "Bitmap_TestCell",
     "registers": {0: 0x02000100, 1: 10}, "memory": [(0x020001B5, 1, 0)],
     "return": 0, "calls": []},
    {"address": 0x080095B4, "name": "Bitmap_LoadCell", "registers": {0: 0x02001000},
     "memory": [(0x02001000, 4, 1), (0x02001004, 4, 10)],
     "stubs": {0x08003E42: {0: 1}}, "writes": [(0x02001004, 4, 1)],
     "calls": [(0x080095C2, 0x08003E42)]},
    {"address": 0x080095B4, "name": "Bitmap_LoadCell", "registers": {0: 0x02001000},
     "memory": [(0x02001000, 4, 1), (0x02001004, 4, 10)],
     "stubs": {0x08003E42: {0: 0}}, "writes": [(0x02001004, 4, 0)],
     "calls": [(0x080095C2, 0x08003E42)]},
    {"address": 0x080095CA, "name": "Bitmap_LoadCellInverted", "registers": {0: 0x02001000},
     "memory": [(0x02001000, 4, 1), (0x02001004, 4, 10)],
     "stubs": {0x08003E42: {0: 1}}, "writes": [(0x02001004, 4, 0)],
     "calls": [(0x080095D8, 0x08003E42)]},
    {"address": 0x080095CA, "name": "Bitmap_LoadCellInverted", "registers": {0: 0x02001000},
     "memory": [(0x02001000, 4, 1), (0x02001004, 4, 10)],
     "stubs": {0x08003E42: {0: 0}}, "writes": [(0x02001004, 4, 1)],
     "calls": [(0x080095D8, 0x08003E42)]},
    {"address": 0x08006078, "name": "Point_StoreScaled",
     "registers": {0: 0x02000100, 1: 0x02000200},
     "memory": [(0x02000200, 4, 0x1000), (0x02000204, 4, 0x2000),
                (0x02000124, 4, 0x100), (0x02000128, 4, 0x200)],
     "return": 0x02000100,
     "writes": [(0x02000104, 4, 0x1000), (0x02000108, 4, 0x2000),
                (0x0200010C, 4, 4), (0x02000110, 4, 8),
                (0x02000114, 4, 0xF4), (0x02000118, 4, 0xA8),
                (0x0200011C, 4, 4), (0x02000120, 4, 8)], "calls": []},
]


def check_cases(cases):
    for case in cases:
        assert any(key in case for key in ("return", "writes", "calls", "writes_len",
                                          "reads")), case["name"]
        result = run_case(case)
        low, high = case.get("low", 0x02000000), case.get("high", 0x03007000)
        skip = case.get("skip")
        written = [entry for entry in writes_between(result, low, high)
                   if skip is None or not skip[0] <= entry[0] < skip[1]]
        if "return" in case:
            assert result["registers"][0] == case["return"], case["name"]
        if "writes" in case:
            assert written == case["writes"], case["name"]
        if "writes_len" in case:
            assert len(written) == case["writes_len"], case["name"]
        if "writes_head" in case:
            assert written[:len(case["writes_head"])] == case["writes_head"], case["name"]
        if "writes_tail" in case:
            assert written[-len(case["writes_tail"]):] == case["writes_tail"], case["name"]
        if "reads" in case:
            for address, size, value in case["reads"]:
                assert result["memory"].read(address, size) == value, (case["name"], address)
        if "calls" in case:
            assert result["calls"] == case["calls"], case["name"]


def test_the_first_batch_asserts_the_recorded_body_effects():
    check_cases(CASES)


def test_the_second_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_TWO)


def test_the_third_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_THREE)


def test_the_fourth_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_FOUR)


def test_the_fifth_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_FIVE)


def run_case(case):
    data = image()
    memory = thumb_vm.Memory(data)
    for seed in case.get("memory", []):
        if len(seed) == 2:
            memory.blob(seed[0], seed[1])
        else:
            memory.write(seed[0], seed[1], seed[2])
    memory.writes.clear()
    result = thumb_vm.run_function(data, case["address"], registers=case.get("registers"),
                                   memory=memory, body=thumb_vm.body_of(data, case["address"]),
                                   stubs=case.get("stubs"))
    result["memory"] = memory
    return result


