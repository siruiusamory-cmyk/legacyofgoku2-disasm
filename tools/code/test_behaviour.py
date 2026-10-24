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
    {"address": 0x08004214, "name": "Character_GetLevel",
     "registers": {0: 0x02000100}, "memory": [(0x02000110, 4, 0x15E6B71)],
     "return": 0x32, "calls": []},
    {"address": 0x08004214, "name": "Character_GetLevel",
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
    {"address": 0x0800426A, "name": "Character_GetLevelThreshold", "registers": {0: 2},
     "return": 0x32, "calls": []},
    {"address": 0x0800426A, "name": "Character_GetLevelThreshold", "registers": {0: 3},
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


CASES_SIX = [
    {"address": 0x0801EFA4, "name": "Heap_Init", "registers": {},
     "return": 0x02000800,
     "writes": [(0x030022B4, 4, 0x02000800), (0x02000800, 2, 0), (0x02000802, 2, 0xFDFE),
                (0x02000804, 2, 0), (0x02000806, 1, 0), (0x02000808, 2, 0),
                (0x0200080A, 2, 0)], "calls": []},
    {"address": 0x08006534, "name": "Table_LinkNode", "registers": {0: 0x02000100, 1: 3},
     "memory": [(0x02000100, 1, 0xFF)], "return": 0x02000100,
     "writes": [(0x020007B2, 1, 0), (0x020007BB, 1, 0xFF), (0x020007BA, 1, 0xFF),
                (0x02000100, 1, 3)], "calls": []},
    {"address": 0x08006534, "name": "Table_LinkNode", "registers": {0: 0x02000100, 1: 3},
     "memory": [(0x02000100, 1, 2)], "return": 0x02000100,
     "writes": [(0x020007B2, 1, 0), (0x020007BB, 1, 0xFF), (0x020007BA, 1, 2),
                (0x020007B1, 1, 3), (0x02000100, 1, 3)], "calls": []},
    {"address": 0x0800656A, "name": "Table_FreeNode", "registers": {0: 0x02000100, 1: 3},
     "memory": [(0x02000101, 1, 0xFF)], "return": 0x02000100,
     "writes": [(0x020007B2, 1, 0xFF), (0x020007B9, 1, 0xFF), (0x020007B8, 1, 0xFF),
                (0x02000101, 1, 3)], "calls": []},
    {"address": 0x0800656A, "name": "Table_FreeNode", "registers": {0: 0x02000100, 1: 3},
     "memory": [(0x02000101, 1, 2)], "return": 0x02000100,
     "writes": [(0x020007B2, 1, 0xFF), (0x020007B9, 1, 0xFF), (0x020007B8, 1, 2),
                (0x020007AF, 1, 3), (0x02000101, 1, 3)], "calls": []},
    {"address": 0x080067AC, "name": "Table_TakeNode", "registers": {0: 0x02000100, 1: 0x80},
     "memory": [(0x02000100, 1, 0), (0x02000796, 2, 0x20), (0x02000798, 2, 2),
                (0x0200079C, 1, 0xFF)],
     "return": 0x40, "writes": [(0x02000794, 1, 1), (0x02000D20, 1, 0)],
     "calls": [(0x080067DA, 0x08006618)]},
    {"address": 0x08002D5C, "name": "Object_InitFromTable",
     "registers": {0: 0x02000100, 1: 0x1234, 2: 0x56, 3: 2},
     "memory": [(0x03007F00, 4, 0xAAAA), (0x03007F04, 4, 0)], "return": 0x02000100,
     "writes": [(0x02000108, 1, 2), (0x02000104, 4, 0x1234), (0x02000109, 1, 0x56),
                (0x02000110, 4, 0x081D8FF4), (0x0200010C, 4, 0xAAAA)], "calls": []},
    {"address": 0x08002D5C, "name": "Object_InitFromTable",
     "registers": {0: 0x02000100, 1: 0x1234, 2: 0x56, 3: 2},
     "memory": [(0x03007F00, 4, 0xAAAA), (0x03007F04, 4, 7)], "return": 0x02000100,
     "writes": [(0x02000108, 1, 0), (0x02000104, 4, 0x1234), (0x02000109, 1, 0x56),
                (0x02000110, 4, 0x081D8FF4), (0x0200010C, 4, 0xAAAA)], "calls": []},
    {"address": 0x0800E310, "name": "Bitmap_FillObjectCells",
     "registers": {0: 0x03000000, 1: 1}, "memory": [(0x0300018D, 1, 0)],
     "stubs": {0x0800793A: {}, 0x080063E0: {}},
     "calls": [(0x0800E328, 0x0800793A), (0x0800E332, 0x080063E0)]},
    {"address": 0x0800E310, "name": "Bitmap_FillObjectCells",
     "registers": {0: 0x03000000, 1: 1}, "memory": [(0x0300018D, 1, 1)],
     "stubs": {0x0800793A: {}, 0x080063E0: {}}, "calls": []},
    {"address": 0x0800E41C, "name": "Bitmap_FillRectCells",
     "registers": {0: 0x03000000, 1: 0x02000200, 2: 1},
     "memory": [(0x0300018D, 1, 0)], "stubs": {0x080063E0: {}},
     "calls": [(0x0800E432, 0x080063E0)]},
    {"address": 0x0800E41C, "name": "Bitmap_FillRectCells",
     "registers": {0: 0x03000000, 1: 0x02000200, 2: 1},
     "memory": [(0x0300018D, 1, 1)], "stubs": {0x080063E0: {}}, "calls": []},
    {"address": 0x0800E45E, "name": "Bitmap_RectIsBlocked",
     "registers": {0: 0x03000000, 1: 0x02000200}, "memory": [(0x0300018D, 1, 0)],
     "stubs": {0x080063B6: {0: 0}}, "return": 0, "calls": [(0x0800E474, 0x080063B6)]},
    {"address": 0x0800E45E, "name": "Bitmap_RectIsBlocked",
     "registers": {0: 0x03000000, 1: 0x02000200}, "memory": [(0x0300018D, 1, 0)],
     "stubs": {0x080063B6: {0: 1}}, "return": 1, "calls": [(0x0800E474, 0x080063B6)]},
    {"address": 0x0800E45E, "name": "Bitmap_RectIsBlocked",
     "registers": {0: 0x03000000, 1: 0x02000200}, "memory": [(0x0300018D, 1, 1)],
     "stubs": {0x080063B6: {0: 0}}, "return": 1, "calls": []},
    {"address": 0x0802153E, "name": "Checksum_Accumulate",
     "registers": {0: 0x02000200, 1: 3}, "memory": [(0x02000200, b"abc")],
     "stubs": {0x08027F1C: {0: 1}}, "return": 0x10001,
     "calls": [(0x0802157A, 0x08027F1C), (0x08021582, 0x08027F1C)]},
    {"address": 0x08016C48, "name": "Sprite_LoadFrameTiles",
     "registers": {0: 0, 1: 0x11, 2: 0x22},
     "stubs": {0x0801F08C: {0: 0x02000100}, 0x080067AC: {0: 5}, 0x0802141C: {0: 2}},
     "return": 0x02000100, "high": 0x04000200, "skip": (0x03007000, 0x03008000),
     "writes": [(0x02000100, 4, 0x08023A1C), (0x0200010E, 2, 0x100), (0x0200010C, 2, 5),
                (0x02000100, 4, 0x0802599C), (0x02000110, 4, 2), (0x02000114, 4, 0x11),
                (0x02000118, 4, 0x22), (0x040000D4, 4, 0x03000C9C),
                (0x040000D8, 4, 0x060100A0), (0x040000DC, 2, 0x10),
                (0x040000DE, 2, 0x8400)],
     "calls": [(0x08016C56, 0x0801F08C), (0x08016C72, 0x080067AC),
               (0x08016C7E, 0x0802141C)]},
    {"address": 0x0800B4AE, "name": "Object_Register",
     "registers": {0: 0, 1: 0x02000300, 2: 0x02000400, 3: 0x02000500},
     "memory": [(0x03007F00, 4, 0x66), (0x02000500, 4, 0x11), (0x02000504, 4, 0x22),
                (0x02000400, 2, 0x40)],
     "stubs": {0x0801F08C: {0: 0x02000100}, 0x08006DA6: {0: 1}}, "return": 0x02000100,
     "writes": [(0x02000100, 4, 0x02000300), (0x02000104, 4, 0x02000400),
                (0x0200010C, 4, 0x11), (0x02000110, 4, 0x22), (0x02000118, 4, 0),
                (0x02000114, 4, 0x66), (0x03001FD8, 4, 0), (0x02000108, 2, 0x40),
                (0x03001FDC, 4, 1)],
     "calls": [(0x0800B4C0, 0x0801F08C), (0x0800B4F4, 0x08006DA6)]},
    {"address": 0x0800B4AE, "name": "Object_Register",
     "registers": {0: 0x02000100, 1: 0x02000300, 2: 0x02000400, 3: 0x02000500},
     "memory": [(0x03007F00, 4, 0x66), (0x02000500, 4, 0x11), (0x02000504, 4, 0x22),
                (0x02000400, 2, 0x40)],
     "stubs": {0x08006DA6: {0: 1}}, "return": 0x02000100,
     "calls": [(0x0800B4F4, 0x08006DA6)]},
    {"address": 0x0800B4FC, "name": "Object_Unregister",
     "registers": {0: 0x02000100, 1: 1},
     "stubs": {0x08006DA6: {0: 1}, 0x0801F110: {}},
     "writes": [(0x03001FDC, 4, 0)],
     "calls": [(0x0800B510, 0x08006DA6), (0x0800B51A, 0x0801F110)]},
    {"address": 0x0800B4FC, "name": "Object_Unregister",
     "registers": {0: 0x02000100, 1: 0},
     "stubs": {0x08006DA6: {0: 1}}, "writes": [(0x03001FDC, 4, 0)],
     "calls": [(0x0800B510, 0x08006DA6)]},
]


CASES_SEVEN = [
    {"address": 0x08001DEA, "name": "Record_ReadByte", "registers": {0: 0x02000100, 1: 0},
     "memory": [(0x02000100, b"\x11\x22\x33")], "return": 0x11, "calls": []},
    {"address": 0x08001DEA, "name": "Record_ReadByte", "registers": {0: 0x02000100, 1: 1},
     "memory": [(0x02000100, b"\x11\x22\x33")], "return": 0x22, "calls": []},
    {"address": 0x08001DEA, "name": "Record_ReadByte", "registers": {0: 0x02000100, 1: 2},
     "memory": [(0x02000100, b"\x11\x22\x33")], "return": 0x33, "calls": []},
    {"address": 0x08001DEA, "name": "Record_ReadByte", "registers": {0: 0x02000100, 1: 3},
     "memory": [(0x02000100, b"\x11\x22\x33")], "return": 0, "calls": []},
    {"address": 0x08002DB6, "name": "Object_ClearState", "registers": {0: 0x02000100},
     "memory": [(0x02000100, 4, 0x02000200), (0x02000200, 4, 8)],
     "return": 0x02000100, "writes": [(0x02000108, 1, 0)],
     "calls": [(0x08002DC2, 0x08021D2A)]},
    {"address": 0x080068A6, "name": "Sprite_LoadNode", "registers": {0: 0x02000100},
     "memory": [(0x0200010E, 2, 0x80)], "stubs": {0x080067AC: {0: 7}}, "return": 7,
     "writes": [(0x0200010C, 2, 7)], "calls": [(0x080068B0, 0x080067AC)]},
    {"address": 0x08019B30, "name": "Scene_New",
     "registers": {0: 0x02000100, 1: 0x02000200, 2: 0x02000300},
     "stubs": {0x080075A8: {}}, "return": 0x02000100,
     "writes": [(0x02000100, 4, 0x0802593C), (0x02000250, 4, 0)],
     "calls": [(0x08019B34, 0x080075A8)]},
    {"address": 0x0800501E, "name": "Sprite_LoadTiles", "registers": {0: 0x02000100},
     "memory": [(0x02000100, 2, 1), (0x02000102, 2, 3), (0x02000104, 4, 0x02000200),
                (0x02000201, 1, 2), (0x02000202, 2, 3), (0x02000208, 4, 0x080E1000)],
     "stubs": {0x080236A8: {}}, "high": 0x04000200, "skip": (0x03007000, 0x03008000),
     "return": 0x8400,
     "writes": [(0x040000D4, 4, 0x03006EF4), (0x040000D8, 4, 0x060000C0),
                (0x040000DC, 2, 0x20), (0x040000DE, 2, 0x8400)],
     "calls": [(0x08005038, 0x080236A8)]},
    {"address": 0x0800501E, "name": "Sprite_LoadTiles", "registers": {0: 0x02000100},
     "memory": [(0x02000100, 2, 0xFFFF), (0x02000104, 4, 0x02000200),
                (0x02000201, 1, 1), (0x02000202, 2, 5), (0x02000204, 4, 0x080E1000)],
     "stubs": {0x080236A8: {}}, "high": 0x04000200, "skip": (0x03007000, 0x03008000),
     "return": 0x8400,
     "writes": [(0x040000D4, 4, 0x03006EF4), (0x040000D8, 4, 0x06000140),
                (0x040000DC, 2, 0x10), (0x040000DE, 2, 0x8400)],
     "calls": [(0x08005038, 0x080236A8)]},
]


CASES_EIGHT = [
    {"address": 0x0800CB50,
     "name": "Buffer_Init",
     "registers": {0: 0x02000100, 1: 0x00000200},
     "stubs": {0x08021F30: {0: 0x2000200}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8023FE4), (0x02000105, 1, 0x40), (0x02000114, 4, 0x200), (0x0200010C, 4, 0x2000200), (0x02000108, 4, 0x0), (0x02000110, 4, 0x2000)],
     "calls": [(0x0800CB6E, 0x08021F30)]},
    {"address": 0x0800D1AC,
     "name": "Vector_SetDirection",
     "registers": {0: 0x02000100, 1: 0x02000200, 2: 0x02000300},
     "memory": [(0x02000204, 0x2, 0x0), (0x02000206, 0x2, 0x0), (0x02000208, 0x2, 0x40), (0x02000358, 0x4, 0x00000100), (0x0200035C, 0x4, 0x00000100)],
     "stubs": {0x08021F30: {0: 0x100}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8023FD4), (0x0200010C, 4, 0x0), (0x02000112, 1, 0x3), (0x02000110, 2, 0x1), (0x02000310, 1, 0x3), (0x02000104, 4, 0x100), (0x02000108, 4, 0x100)],
     "calls": [(0x0800D238, 0x08021F30), (0x0800D256, 0x08021F30), (0x0800D262, 0x08021F30)]},
    {"address": 0x0800EB7C,
     "name": "Table_FindByPair",
     "registers": {0: 0x00000001, 1: 0x00000001},
     "stubs": {0x0800E0AC: {0: 0x2}},
     "return": 0x8409368,
     "calls": [(0x0800EB82, 0x0800E0AC)]},
    {"address": 0x0800C7AE,
     "name": "Scene_Install",
     "registers": {0: 0x02000100},
     "memory": [(0x02000100, 0x4, 0x11), (0x02000104, 0x4, 0x22), (0x02000108, 0x4, 0x33), (0x0200010C, 0x4, 0x44)],
     "stubs": {0x08006460: {}, 0x08006F4A: {}},
     "return": 0x3001120,
     "writes": [(0x03002070, 4, 0x11), (0x03002074, 4, 0x22), (0x03002078, 4, 0x33), (0x0300207C, 4, 0x44)],
     "calls": [(0x0800C7BA, 0x08006460), (0x0800C7C0, 0x08006F4A)]},
    {"address": 0x0800DF1C,
     "name": "Scene_Publish",
     "registers": {0: 0x02000100, 1: 0x00000001, 2: 0x00000002},
     "stubs": {0x0800DCA8: {}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8025A40), (0x03000FF4, 4, 0x30020C8)],
     "calls": [(0x0800DF42, 0x0800DCA8)]},
    {"address": 0x080086D4,
     "name": "Sprite_SetDirectory",
     "registers": {0: 0x00000000, 1: 0x00000003, 2: 0x00000004},
     "memory": [(0x030021E0, 0x4, 0x02000400), (0x02000400, 0x4, 0x02000500), (0x02000500, 0x4, 0x02000600)],
     "stubs": {0x0800F80C: {}, 0x0801F08C: {0: 0x2000100}, 0x08021D2C: {}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8025604), (0x03001FA8, 4, 0x2000100), (0x02000290, 4, 0x0), (0x02000294, 4, 0x0), (0x02000298, 4, 0x0), (0x0200029C, 4, 0x0), (0x02000280, 4, 0x30021E0)],
     "calls": [(0x080086E4, 0x0801F08C), (0x080086F8, 0x0800F80C), (0x0800873A, 0x08021D2C)]},
    {"address": 0x0800BDCC,
     "name": "Scene_GetEntry",
     "registers": {0: 0x00000001},
     "stubs": {0x08026440: {}},
     "return": 0x3000E9C,
     "calls": [(0x0800BDE8, 0x08026440)]},
    {"address": 0x0800BDCC,
     "name": "Scene_GetEntry",
     "registers": {0: 0x00000009},
     "memory": [(0x03000E90, 0x1, 0x0)],
     "return": 0x86AFA08,
     "calls": []},
    {"address": 0x08019B48,
     "name": "Scene_Destroy",
     "registers": {0: 0x02000100},
     "memory": [(0x02000250, 0x4, 0x02000300), (0x02000300, 0x4, 0x02000400), (0x02000400, 0x4, 0x02000500)],
     "stubs": {0x080075F8: {}, 0x08021D2C: {}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x802593C)],
     "calls": [(0x08019B62, 0x08021D2C), (0x08019B6A, 0x080075F8)]},
    {"address": 0x08026440,
     "name": "Scene_SelectCode",
     "registers": {0: 0x02000100},
     "memory": [(0x02000108, 0x1, 0x5)],
     "stubs": {0x0800BDCC: {0: 0x2000400}},
     "return": 0x2000400,
     "calls": [(0x08026450, 0x0800BDCC)]},
    {"address": 0x0800FCCC,
     "name": "Bitmap_NewTile",
     "registers": {0: 0x00000000, 1: 0x02000200, 2: 0x02000300},
     "memory": [(0x02000200, 0x4, 0x3), (0x02000204, 0x4, 0x4), (0x02000208, 0x4, 0x5), (0x02000300, 0x4, 0x10), (0x02000304, 0x4, 0x10)],
     "stubs": {0x080067AC: {0: 0x6}, 0x0800FC84: {}, 0x0801F08C: {0: 0x2000100}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8023A1C), (0x0200010E, 2, 0xC), (0x0200010C, 2, 0x6), (0x02000100, 4, 0x80245E8), (0x02000114, 4, 0x2000200), (0x02000110, 4, 0x5), (0x02000118, 4, 0x10), (0x0200011C, 4, 0x10), (0x02000124, 4, 0x14), (0x02000120, 4, 0x13), (0x02000104, 4, 0x14)],
     "calls": [(0x0800FCDC, 0x0801F08C), (0x0800FCFA, 0x080067AC), (0x0800FD36, 0x0800FC84)]},
    {"address": 0x080104C0,
     "name": "Sprite_NewSpan",
     "registers": {0: 0x00000000, 1: 0x00000002, 2: 0x00000005, 3: 0x00000009},
     "stubs": {0x080067AC: {0: 0x7}, 0x0801F08C: {0: 0x2000100}, 0x08027EF8: {1: 0x4}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8023A1C), (0x0200010E, 2, 0x200), (0x0200010C, 2, 0x7), (0x02000100, 4, 0x8025748), (0x02000110, 4, 0x2), (0x02000114, 1, 0xFF), (0x02000108, 1, 0x4), (0x02000104, 4, 0x0), (0x02000118, 1, 0xF8), (0x02000117, 1, 0x1), (0x02000115, 1, 0x4), (0x02000116, 1, 0x0)],
     "calls": [(0x080104D0, 0x0801F08C), (0x080104EC, 0x080067AC), (0x08010512, 0x08027EF8), (0x08010520, 0x08027EF8)]},
    {"address": 0x0800FA6C,
     "name": "Bitmap_NewFromDefinition",
     "registers": {0: 0x00000000, 1: 0x02000200},
     "memory": [(0x02000204, 0x4, 0x3)],
     "stubs": {0x080063E0: {}, 0x0800FCCC: {}, 0x0800FE2E: {}, 0x0801F08C: {0: 0x2000100}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8024230), (0x02000130, 4, 0x2000200), (0x02000108, 1, 0x28)],
     "calls": [(0x0800FA78, 0x0801F08C), (0x0800FA98, 0x0800FCCC), (0x0800FAAE, 0x0800FE2E), (0x0800FABC, 0x080063E0), (0x0800FAC6, 0x080063E0)]},
    {"address": 0x0800F1AE,
     "name": "Sprite_DrawDirections",
     "registers": {0: 0x02000100},
     "memory": [(0x02000110, 0x4, 0x1), (0x02000114, 0x4, 0x2), (0x02000118, 0x4, 0x3), (0x0200011C, 0x4, 0x4), (0x0200010C, 0x1, 0x2)],
     "stubs": {0x080068B8: {}, 0x08006D70: {0: 0x800}, 0x0800EC08: {0: 0x2000300}, 0x080135E0: {0: 0x2000400}, 0x0801F08C: {0: 0x2000200}, 0x0802141C: {0: 0x1}},
     "return": 0x17,
     "writes": [(0x0200010C, 1, 0x1), (0x02000120, 4, 0x17)],
     "calls": [(0x0800F1E2, 0x0800EC08), (0x0800F1EC, 0x080068B8), (0x0800F1F8, 0x0800EC08), (0x0800F200, 0x080068B8), (0x0800F20C, 0x0800EC08), (0x0800F214, 0x080068B8), (0x0800F220, 0x0800EC08), (0x0800F228, 0x080068B8)]},
    {"address": 0x0800B84E,
     "name": "Sprite_AdvanceSlots",
     "registers": {0: 0x02000100},
     "memory": [(0x0200015F, 0x1, 0x11), (0x02000160, 0x1, 0x22), (0x02000161, 0x1, 0x33), (0x0200017F, 0x1, 0x44), (0x02000180, 0x1, 0x55), (0x02000181, 0x1, 0x66)],
     "stubs": {0x0801F7E2: {}},
     "return": 0x0,
     "writes_len": 30,
     "writes_head": [(0x0200015C, 1, 0x11), (0x0200015D, 1, 0x22), (0x0200015E, 1, 0x33), (0x020001A5, 1, 0x9)],
     "calls": [(0x0800B882, 0x0801F7E2)]},
    {"address": 0x08021344,
     "name": "Sprite_PublishWords",
     "registers": {0: 0x02000100, 1: 0x02000200},
     "memory": [(0x0200012C, 0x4, 0x11), (0x02000130, 0x4, 0x22)],
     "stubs": {0x080236CC: {}},
     "return": 0x2000100,
     "writes": [(0x03003888, 4, 0x11), (0x0300388C, 4, 0x22)],
     "calls": [(0x08021350, 0x080236CC)]},
    {"address": 0x080214C4,
     "name": "Dma_CopySpan",
     "registers": {0: 0x02000100, 1: 0x00000010, 2: 0x08001000, 3: 0x00000020},
     "memory": [(0x02000100, 0x4, 0x1), (0x03003898, 0x4, 0x03004000)],
     "stubs": {0x08020BBA: {}, 0x08020BD0: {}, 0x08021CB0: {}},
     "return": 0x30026BC,
     "high": 0x04000300,
     "skip": (0x03007000, 0x04000000),
     "writes": [(0x040000D4, 4, 0x8001000), (0x040000D8, 4, 0x3004010), (0x040000DC, 2, 0x8), (0x040000DE, 2, 0x8400), (0x04000200, 2, 0x2040), (0x04000200, 2, 0x0)],
     "calls": [(0x080214EC, 0x08020BBA), (0x0802150C, 0x08021CB0), (0x0802150C, 0x08021CB0), (0x0802150C, 0x08021CB0), (0x0802150C, 0x08021CB0), (0x08021520, 0x08020BD0)]},
    {"address": 0x08006FA4,
     "name": "Object_FreeTiles",
     "registers": {0: 0x02000100},
     "memory": [(0x02000C98, 0x4, 0x02000200)],
     "stubs": {0x08006C24: {}, 0x08006DA6: {}, 0x0801F110: {}, 0x0801FDD0: {}, 0x08021EA8: {}},
     "return": 0x2000100,
     "calls": [(0x08006FA8, 0x08006C24), (0x08006FBC, 0x08021EA8), (0x08006FC2, 0x0801F110), (0x08006FD0, 0x0801FDD0), (0x08006FDA, 0x08006DA6)]},
    {"address": 0x08006F4A,
     "name": "Object_ResetTiles",
     "registers": {0: 0x02000100},
     "stubs": {0x08006C24: {}, 0x08006DA6: {}, 0x08006ED0: {}, 0x0801F08C: {0: 0x2000200}, 0x0801FD78: {0: 0x7}, 0x08021EA8: {}},
     "return": 0x2000100,
     "writes": [(0x02000CFC, 4, 0x7), (0x02000CF8, 4, 0x2000200), (0x02000710, 4, 0x0), (0x02000104, 4, 0x0), (0x0200050C, 4, 0x0)],
     "calls": [(0x08006F52, 0x08006DA6), (0x08006F58, 0x08006ED0), (0x08006F64, 0x0801FD78), (0x08006F76, 0x0801F08C), (0x08006F84, 0x08021EA8), (0x08006F9E, 0x08006C24)]},
    {"address": 0x0801F294,
     "name": "Frame_RunUntilDone",
     "memory": [(0x03000E1C, 0x4, 0x02000100), (0x02000100, 0x4, 0x02000200)],
     "stubs": {0x0801EEFC: {}, 0x08020BD8: {}, 0x08020D40: {}, 0x08021D2A: {0: 0x1}},
     "return": 0x1,
     "calls": [(0x0801F2A4, 0x08021D2A), (0x0801F2AA, 0x08020BD8), (0x0801F2B2, 0x08020D40), (0x0801F2B8, 0x0801EEFC), (0x0801F2C4, 0x08021D2A)]},
    {"address": 0x08020A4C,
     "name": "Table_InitRing",
     "registers": {0: 0x02000100, 1: 0x02000200},
     "memory": [(0x02000210, 0x1, 0x2), (0x02000211, 0x1, 0x3)],
     "stubs": {0x08021F30: {0: 0x64}},
     "return": 0x64,
     "writes_len": 84,
     "writes_head": [(0x02000102, 1, 0x1), (0x02000100, 1, 0x1), (0x02000101, 1, 0x0), (0x0200010C, 4, 0x2000200)],
     "calls": [(0x08020A8C, 0x08021F30)]},
]

CASES_NINE = [
    {"address": 0x08000EB8,
     "name": "Sprite_BuildTileset",
     "registers": {0: 0x02000100},
     "memory": [(0x02000100, 0x4, 0x0), (0x0200010C, 0x4, 0x0)],
     "stubs": {0x080019F6: {0: 0x0}, 0x08001A8A: {0: 0x0}, 0x0801F394: {}, 0x08021D2C: {}, 0x080236A8: {}, 0x080236B4: {}},
     "return": 0x0,
     "writes": [(0x02000684, 4, 0x10), (0x02000688, 4, 0x10), (0x0200068C, 4, 0x100), (0x02000670, 4, 0x10), (0x02000674, 4, 0x10), (0x02000690, 4, 0x6007940), (0x02000694, 4, 0x8704CEC), (0x02000684, 4, 0x20), (0x02000688, 4, 0x20), (0x0200068C, 4, 0x400), (0x02000670, 4, 0x20), (0x02000674, 4, 0x20), (0x020006E0, 4, 0x0)],
     "calls": [(0x08000EE0, 0x0801F394), (0x08000EEA, 0x080236B4), (0x08000EF2, 0x0801F394), (0x08000EFA, 0x080236B4), (0x08000F02, 0x0801F394), (0x08000F0A, 0x080236B4), (0x08000F2C, 0x080236A8), (0x08000F34, 0x080236B4), (0x08000F6A, 0x080019F6)]},
    {"address": 0x08005F1A,
     "name": "Display_Commit",
     "registers": {0: 0x02000100, 1: 0x00000000},
     "memory": [(0x02000150, 0x4, 0x02000200), (0x0200023C, 0x4, 0x1), (0x02000178, 0x4, 0x10), (0x0200017C, 0x4, 0x20), (0x02000180, 0x4, 0x30), (0x02000184, 0x4, 0x40), (0x02000160, 0x4, 0x70), (0x02000164, 0x2, 0x50), (0x02000161, 0x1, 0x60), (0x02000162, 0x2, 0x80)],
     "stubs": {0x08005096: {}, 0x080050C8: {}, 0x08005240: {}, 0x08005272: {}},
     "return": 0x80,
     "high": 0x04000300,
     "skip": (0x03007000, 0x04000000),
     "writes": [(0x04000008, 2, 0x1C90), (0x0400000A, 2, 0x1DA0), (0x0400000C, 2, 0xBEB0), (0x0400000E, 2, 0x1FC0), (0x04000050, 2, 0x50), (0x04000052, 1, 0x60), (0x04000053, 1, 0x70), (0x04000000, 2, 0x80)],
     "calls": [(0x08005F52, 0x08005096), (0x08005F5A, 0x08005240), (0x08005F62, 0x080050C8), (0x08005F6A, 0x08005272)]},
    {"address": 0x08006152,
     "name": "Scene_BuildLayers",
     "registers": {0: 0x02000100, 1: 0x02000200, 2: 0x02000300},
     "memory": [(0x02000200, 0x4, 0x00010002), (0x02000208, 0x2, 0x20), (0x0200020A, 0x2, 0x18), (0x02000234, 0x4, 0x080E1000), (0x02000238, 0x4, 0x080E2000), (0x0200023C, 0x4, 0x0), (0x02000204, 0x4, 0x7)],
     "stubs": {0x08005DD4: {}, 0x08005F1A: {}, 0x08005FBA: {}, 0x080060B0: {}, 0x080060FE: {}, 0x0801F08C: {0: 0x2001000}, 0x0801F394: {}, 0x0801F412: {}},
     "return": 0x2000100,
     "writes_len": 24,
     "writes_head": [(0x02000100, 4, 0x0), (0x02000134, 4, 0x0), (0x02000150, 4, 0x2000200), (0x02000124, 4, 0x0)],
     "calls": [(0x0800617A, 0x0801F08C), (0x08006188, 0x0801F08C), (0x08006196, 0x0801F08C), (0x080061A0, 0x0801F394), (0x080061A8, 0x0801F394), (0x080061B4, 0x0801F412), (0x080061D8, 0x08005FBA), (0x0800620E, 0x080060B0), (0x08006244, 0x08005F1A)]},
    {"address": 0x08006AD8,
     "name": "List_CollectFiltered",
     "registers": {0: 0x02000100},
     "memory": [(0x02000104, 0x4, 0x1), (0x02000108, 0x4, 0x02000300), (0x02000300, 0x4, 0x02000400), (0x02000400, 0x4, 0x02000500), (0x0300229C, 0x4, 0x02000600)],
     "stubs": {0x0801F54C: {}, 0x08021D2A: {0: 0x1}, 0x08021D2C: {0: 0x1}, 0x08027E74: {0: 0x1}, 0x08027F40: {}},
     "return": 0x1,
     "writes": [(0x02000308, 4, 0x1), (0x0200030C, 4, 0x2000300)],
     "calls": [(0x08006AFE, 0x08021D2A), (0x08006BCE, 0x0801F54C), (0x08006C00, 0x08021D2C)]},
    {"address": 0x080102A2,
     "name": "Sprite_CreatePastThreshold",
     "registers": {0: 0x02000100, 1: 0x00000002, 2: 0x00000003, 3: 0x00000004},
     "stubs": {0x080068B8: {}, 0x08006D70: {0: 0x100}, 0x08010194: {0: 0x2000500}},
     "return": 0x2000500,
     "calls": [(0x080102B2, 0x08006D70), (0x080102CE, 0x08010194), (0x080102D8, 0x080068B8)]},
    {"address": 0x080102A2,
     "name": "Sprite_CreatePastThreshold",
     "registers": {0: 0x02000100, 1: 0x00000002, 2: 0x00000003, 3: 0x00000004},
     "stubs": {0x080068B8: {}, 0x08006D70: {0: 0x80}, 0x08010194: {0: 0x2000500}},
     "return": 0x0,
     "calls": [(0x080102B2, 0x08006D70)]},
    {"address": 0x08011802,
     "name": "Sprite_NewLayer",
     "registers": {0: 0x00000000, 1: 0x00000000, 2: 0x02000300},
     "memory": [(0x02000300, 0x4, 0x00000100), (0x02000304, 0x4, 0x80)],
     "stubs": {0x080068B8: {}, 0x0800FCCC: {}, 0x0801177C: {}, 0x0801F08C: {0: 0x2000100}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8024C90), (0x02000130, 4, 0x2000), (0x02000140, 4, 0x0), (0x02000134, 4, 0x800), (0x02000138, 4, 0x0), (0x02000108, 1, 0x28), (0x0200013C, 4, 0x0)],
     "calls": [(0x08011812, 0x0801F08C), (0x08011846, 0x0800FCCC)]},
    {"address": 0x08013828,
     "name": "Sprite_ReplaceInList",
     "registers": {0: 0x02000100},
     "memory": [(0x02000120, 0x4, 0x00000300), (0x02000124, 0x4, 0x00000100), (0x030010F8, 0x4, 0x02000200)],
     "stubs": {0x080068B8: {}, 0x080068CA: {}, 0x08006D70: {0: 0x800}, 0x080135E0: {0: 0x2000400}, 0x0801FC9C: {}, 0x0802141C: {0: 0x1}},
     "return": 0x3001120,
     "calls": [(0x0801383E, 0x080068CA), (0x08013846, 0x0802141C), (0x0801385E, 0x0801FC9C), (0x08013864, 0x08006D70), (0x08013882, 0x080135E0), (0x0801388A, 0x080068B8)]},
    {"address": 0x08018540,
     "name": "Scene_NewRoot",
     "registers": {0: 0x00000000},
     "memory": [(0x03002274, 0x4, 0x02000200), (0x02000200, 0x4, 0x0)],
     "stubs": {0x08006DA6: {}, 0x080174A4: {}, 0x0801F08C: {0: 0x2000100}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x80244A8), (0x02000104, 4, 0x80244F0), (0x02000178, 4, 0x0)],
     "calls": [(0x08018548, 0x0801F08C), (0x08018556, 0x080174A4), (0x08018578, 0x08006DA6)]},
    {"address": 0x0801ED3C,
     "name": "Scene_NewMaster",
     "registers": {0: 0x00000000},
     "memory": [(0x030026C8, 0x1, 0x2), (0x030026D4, 0x4, 0x0)],
     "stubs": {0x0801A378: {}, 0x0801F08C: {0: 0x2000100}, 0x08020A4C: {}},
     "return": 0x2000100,
     "writes": [(0x02000100, 4, 0x8023AB8)],
     "calls": [(0x0801ED44, 0x0801F08C), (0x0801ED54, 0x0801A378), (0x0801ED6E, 0x08020A4C)]},
]

CASES_TEN = [
    {"address": 0x0800E0AC,
     "name": "Table_PairCount",
     "return": 0x147,
     "calls": []},
    {"address": 0x0800409E,
     "name": "Record_GetPairEntry",
     "registers": {0: 0x02000100},
     "memory": [(0x02000100, b"\x00\x00\x01\x02")],
     "stubs": {0x0800EB7C: {0: 0x08409368}},
     "return": 0x08409368,
     "calls": [(0x080040A4, 0x0800EB7C)]},
    {"address": 0x08001DC8,
     "name": "Record_SetFieldOne",
     "registers": {0: 0x02000100, 1: 0x22},
     "stubs": {0x0801FD56: {0: 1}},
     "return": 1, "writes": [(0x02000101, 1, 0x22)],
     "calls": [(0x08001DD4, 0x0801FD56)]},
    {"address": 0x08001DDA,
     "name": "Record_SetFieldTwo",
     "registers": {0: 0x02000100, 1: 0x22},
     "stubs": {0x08020AC8: {0: 1}},
     "return": 1, "writes": [(0x02000102, 1, 0x22)],
     "calls": [(0x08001DE4, 0x08020AC8)]},
    {"address": 0x08001E06,
     "name": "Record_SetField",
     "registers": {0: 0x02000100, 1: 0x0, 2: 0x99},
     "return": 0x02000100, "writes": [(0x02000100, 1, 0x99)], "calls": []},
    {"address": 0x08001E06,
     "name": "Record_SetField",
     "registers": {0: 0x02000100, 1: 0x1, 2: 0x99},
     "stubs": {0x0801FD56: {0: 1}},
     "return": 1, "writes": [(0x02000101, 1, 0x99)],
     "calls": [(0x08001E36, 0x0801FD56)]},
    {"address": 0x08001E06,
     "name": "Record_SetField",
     "registers": {0: 0x02000100, 1: 0x2, 2: 0x99},
     "stubs": {0x08020AC8: {0: 1}},
     "return": 1, "writes": [(0x02000102, 1, 0x99)],
     "calls": [(0x08001E24, 0x08020AC8)]},
    {"address": 0x080040AA,
     "name": "Object_SetActive",
     "registers": {0: 0x02000100, 1: 0x1},
     "stubs": {0x08008B14: {0: 0x02000200}, 0x080068B8: {0: 0}},
     "return": 0,
     "writes": [(0x02000101, 1, 0x2), (0x02000224, 4, 0xFFFFFFF0), (0x02000220, 4, 1)],
     "calls": [(0x080040C6, 0x08008B14), (0x080040D8, 0x080068B8)]},
    {"address": 0x080040AA,
     "name": "Object_SetActive",
     "registers": {0: 0x02000100, 1: 0x1},
     "memory": [(0x02000101, 1, 0x2)],
     "return": 0x02000100, "writes": [], "calls": []},
    {"address": 0x080040AA,
     "name": "Object_SetActive",
     "registers": {0: 0x02000100, 1: 0x0},
     "memory": [(0x02000101, 1, 0x2)],
     "stubs": {0x08006E0A: {0: 0}},
     "return": 0, "writes": [(0x02000101, 1, 0)], "calls": [(0x080040E8, 0x08006E0A)]},
    {"address": 0x08003F9C,
     "name": "Scene_LoadSnapshot",
     "registers": {0: 0x02000100, 1: 0x0},
     "memory": [(0x03007EE4, 4, 0x1234)],
     "stubs": {0x0802153E: {0: 0x1234}},
     "return": 0x02000100, "writes": [],
     "calls": [(0x08003FA8, 0x08003C24), (0x08003FBE, 0x08021526),
               (0x08003FCA, 0x0802153E), (0x08003FDC, 0x08021EA8)]},
    {"address": 0x08003F9C,
     "name": "Scene_LoadSnapshot",
     "registers": {0: 0x02000100, 1: 0x0},
     "memory": [(0x03007EE4, 4, 0x1235)],
     "stubs": {0x0802153E: {0: 0x1234}},
     "return": 0x02000100, "writes": [],
     "calls": [(0x08003FA8, 0x08003C24), (0x08003FBE, 0x08021526),
               (0x08003FCA, 0x0802153E), (0x08003FE6, 0x08003C24)]},
    {"address": 0x0800E438,
     "name": "Object_IsBlocked",
     "registers": {0: 0x02000100, 1: 0x02000200},
     "memory": [(0x0200028D, 1, 1)],
     "return": 1, "calls": []},
    {"address": 0x0800E438,
     "name": "Object_IsBlocked",
     "registers": {0: 0x02000100, 1: 0x02000200},
     "stubs": {0x08005D6C: {0: 0}},
     "return": 0, "calls": [(0x0800E44E, 0x08005D6C)]},
    {"address": 0x08005240,
     "name": "Display_CommitLayers",
     "registers": {0: 0x02000100, 1: 0x02000200},
     "memory": [(0x02000100, 4, 0), (0x02000104, 4, 0x02000300), (0x02000108, 4, 0),
                (0x0200010C, 4, 0), (0x02000214, 4, 0x02000400),
                (0x02000218, 4, 0x02000400), (0x0200021C, 4, 0x02000400),
                (0x02000220, 4, 0x02000400), (0x02000300, 4, 0x02000500),
                (0x02000400, 4, 0x30), (0x02000500, 4, 0x10)],
     "stubs": {0x08021D2C: {0: 7}},
     "return": 7,
     "writes": [(0x02000100, 4, 7), (0x02000104, 4, 7), (0x02000108, 4, 7),
                (0x0200010C, 4, 7)],
     "calls": [(0x08005264, 0x08021D2C), (0x08005258, 0x08021D2C),
               (0x08005264, 0x08021D2C), (0x08005264, 0x08021D2C),
               (0x08005264, 0x08021D2C)]},
    {"address": 0x08026620,
     "name": "Record_NewFromWords",
     "registers": {0: 0, 1: 0x02000200},
     "memory": [(0x02000200, 4, 0x11), (0x02000204, 4, 0x22)],
     "stubs": {0x0801F08C: {0: 0x02000100}},
     "return": 0x02000100,
     "writes": [(0x02000104, 4, 0), (0x02000108, 4, 0), (0x0200010C, 4, 0),
                (0x02000100, 4, 0x08024A8C), (0x02000110, 4, 0x11),
                (0x02000114, 4, 0x22)],
     "calls": [(0x0802662A, 0x0801F08C)]},
]

CASES_ELEVEN = [
    {"address": 0x0801F58C,
     "name": "Surface_InitFromDescription",
     "registers": {0: 0, 1: 0x33, 2: 0x02000200},
     "memory": [(0x02000200, 4, 0x11), (0x02000204, 4, 0x22), (0x02000208, 4, 0x33),
                (0x0200020C, 4, 0x44)],
     "stubs": {0x0801F08C: {0: 0x02000100}},
     "return": 0x02000100,
     "writes": [(0x02000110, 4, 0x11), (0x02000114, 4, 0x22), (0x02000118, 4, 0x33),
                (0x0200011C, 4, 0x44), (0x0200010C, 4, 0x33), (0x02000100, 1, 0),
                (0x02000101, 1, 0), (0x02000104, 4, 0x11), (0x02000108, 4, 0x2E)],
     "calls": [(0x0801F598, 0x0801F08C)]},
    {"address": 0x0800BF08,
     "name": "Queue_Clear",
     "registers": {0: 0x02000100},
     "memory": [(0x02000100, 4, 2), (0x02000108, 4, 0x02000300), (0x02000188, 4, 7),
                (0x02000300, 4, 0x02000400), (0x02000400, 4, 0x10)],
     "stubs": {0x08021D2C: {0: 0}},
     "return": 8,
     "writes": [(0x02000100, 4, 0), (0x02000184, 4, 1), (0x0200018C, 4, 0),
                (0x02000188, 4, 8)],
     "calls": [(0x0800BF24, 0x08021D2C)]},
    {"address": 0x0800BF6E,
     "name": "Queue_RemoveObject",
     "registers": {0: 0x02000100, 1: 0x02000300},
     "memory": [(0x02000100, 4, 3), (0x02000104, 4, 0x111),
                (0x02000108, 4, 0x02000300), (0x0200010C, 4, 0x333),
                (0x02000300, 4, 0x02000400), (0x02000400, 4, 0x10)],
     "stubs": {0x08021D2C: {0: 0}},
     "return": 0,
     "high": 0x04000300,
     "skip": (0x03007000, 0x04000000),
     "writes": [(0x02000100, 4, 2), (0x040000D4, 4, 0x0200010C),
                (0x040000D8, 4, 0x02000108), (0x040000DC, 2, 1),
                (0x040000DE, 2, 0x8400)],
     "calls": [(0x0800BFBA, 0x08021D2C)]},
    {"address": 0x0800EB20,
     "name": "Record_ResolveWord",
     "registers": {0: 0x02000100, 1: 0x55},
     "return": 0x55, "calls": []},
    {"address": 0x0800EB20,
     "name": "Record_ResolveWord",
     "registers": {0: 0x02000100, 1: 0},
     "memory": [(0x02000128, 4, 0)],
     "return": 1, "calls": []},
    {"address": 0x0800EB20,
     "name": "Record_ResolveWord",
     "registers": {0: 0x02000100, 1: 0},
     "memory": [(0x02000128, 4, 0x086D5194), (0x03007EA8, 4, 0x77)],
     "stubs": {0x080092E4: {}},
     "return": 0x77, "calls": [(0x0800EB44, 0x080092E4)]},
    {"address": 0x08019102,
     "name": "Table_FindByDirectory",
     "registers": {0: 0x02000000},
     "stubs": {0x08009324: {0: 0x02000000}},
     "return": 0, "calls": [(0x08019114, 0x08009324)]},
    {"address": 0x08019102,
     "name": "Table_FindByDirectory",
     "registers": {0: 0x02000001},
     "stubs": {0x08009324: {0: 0x02000000}},
     "return": 0xFFFFFFFF, "calls_len": 128},
    {"address": 0x08008B14,
     "name": "Sprite_NewInstance",
     "registers": {0: 0},
     "stubs": {0x0801F08C: {0: 0x02000100}, 0x080067AC: {0: 5}},
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 0x08023A1C), (0x0200010E, 2, 0x500),
                (0x0200010C, 2, 5), (0x02000100, 4, 0x0802408C),
                (0x02000108, 1, 4), (0x02000104, 4, 0), (0x02000124, 4, 8),
                (0x02000120, 4, 0), (0x02000110, 1, 0xFF), (0x02000114, 1, 0),
                (0x02000118, 4, 0)],
     "calls": [(0x08008B1C, 0x0801F08C), (0x08008B38, 0x080067AC)]},
    {"address": 0x08013BC0,
     "name": "Sprite_NewFrame",
     "registers": {0: 0x02000100, 1: 0x1234, 2: 0x02000200},
     "memory": [(0x02000210, 1, 0x5A), (0x0200036C, 4, 0x77)],
     "stubs": {0x080067AC: {0: 7}},
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 0x08023A1C), (0x0200010E, 2, 0x1234),
                (0x0200010C, 2, 7), (0x02000100, 4, 0x08024F38),
                (0x02000110, 4, 0), (0x0200011C, 4, 0x02000200),
                (0x02000114, 1, 0x5A), (0x02000115, 1, 0x77)],
     "calls": [(0x08013BD0, 0x080067AC)]},
    {"address": 0x08016E8C,
     "name": "Sprite_NewEntry",
     "registers": {0: 0, 1: 0x02000200, 2: 0x10, 3: 4},
     "memory": [(0x02000214, 2, 0x30), (0x02000216, 1, 1)],
     "stubs": {0x0801F08C: {0: 0x02000100}},
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 0x08025D20), (0x02000114, 4, 0x02000200),
                (0x0200010C, 2, 0x10), (0x0200010E, 2, 0x34), (0x02000110, 4, 1)],
     "calls": [(0x08016E9A, 0x0801F08C)]},
]

CASES_TWELVE = [
    {"address": 0x080093DA,
     "name": "Opcode_PushOperandOne",
     "registers": {0: 0x02000100},
     "memory": [(0x03001FAC, 4, 0x02000200), (0x02000200, 4, 0xA0)],
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 1), (0x02000104, 4, 0xA0)], "calls": []},
    {"address": 0x080093EE,
     "name": "Opcode_PushOperandTwo",
     "registers": {0: 0x02000100},
     "memory": [(0x03001FAC, 4, 0x02000200), (0x02000204, 4, 0xA4)],
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 1), (0x02000104, 4, 0xA4)], "calls": []},
    {"address": 0x08009402,
     "name": "Opcode_PushOperandThree",
     "registers": {0: 0x02000100},
     "memory": [(0x03001FAC, 4, 0x02000200), (0x02000208, 4, 0xA8)],
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 1), (0x02000104, 4, 0xA8)], "calls": []},
    {"address": 0x08009416,
     "name": "Opcode_PushOperandFour",
     "registers": {0: 0x02000100},
     "memory": [(0x03001FAC, 4, 0x02000200), (0x0200020C, 4, 0xAC)],
     "return": 0x02000100,
     "writes": [(0x02000100, 4, 1), (0x02000104, 4, 0xAC)], "calls": []},
]

CASES_THIRTEEN = [
    {"address": 0x08004230,
     "name": "Character_GetXpToNextLevel",
     "registers": {0: 0x02000100},
     "memory": [(0x02000110, 4, 0)],
     "return": 0x32, "calls": []},
    {"address": 0x08004230,
     "name": "Character_GetXpToNextLevel",
     "registers": {0: 0x02000100},
     "memory": [(0x02000110, 4, 0x15E6B71)],
     "return": 0, "calls": []},
    {"address": 0x0800425A,
     "name": "Character_GetXpIntoLevel",
     "registers": {0: 0x02000100, 1: 2},
     "memory": [(0x02000110, 4, 150)],
     "return": 0x64, "calls": []},
    {"address": 0x08004276,
     "name": "Character_SetXpForLevel",
     "registers": {0: 0x02000100, 1: 2},
     "return": 0x2000100,
     "writes": [(0x02000110, 4, 0x32)], "calls": []},
    {"address": 0x08004276,
     "name": "Character_SetXpForLevel",
     "registers": {0: 0x02000100, 1: 5},
     "return": 0x2000100,
     "writes": [(0x02000110, 4, 0x258)], "calls": []},
    {"address": 0x08003D58,
     "name": "Character_AwardXp",
     "registers": {0: 0x02000000, 1: 0, 2: 60},
     "memory": [(0x0200000C, 2, 5), (0x0200001C, 4, 0)],
     "return": 0x200000C,
     "writes": [(0x0200001C, 4, 60)],
     "calls": [(0x08003D72, 0x08004214), (0x08003D82, 0x08004214)]},
    {"address": 0x08003D58,
     "name": "Character_AwardXp",
     "registers": {0: 0x02000000, 1: 0, 2: 60},
     "memory": [(0x0200000C, 2, 0), (0x0200001C, 4, 0)],
     "return": 0,
     "writes": [], "calls": []},
    {"address": 0x08003CA0,
     "name": "Character_ApplyLevelUp",
     "registers": {0: 0x02000000, 1: 0, 2: 1, 3: 2},
     "memory": [(0x0200000C, 2, 0x0A00), (0x0200000E, 2, 0x0A00),
                (0x02000010, 2, 7), (0x02000012, 2, 7),
                (0x02000016, 2, 0x100), (0x02000018, 2, 0x200),
                (0x0200001A, 2, 0x300)],
     "stubs": {0x08003C6E: {0: 1}, 0x0802141C: {0: 0x500}},
     "return": 0,
     "writes": [(0x0200000E, 2, 0x0ABE), (0x0200000C, 2, 0x0ABE),
                (0x02000012, 2, 0x509), (0x02000010, 2, 0x509),
                (0x03001FC1, 1, 0), (0x03001FC2, 1, 0), (0x03001FC3, 1, 0)],
     "calls": [(0x08003CDC, 0x08003C6E), (0x08003CE8, 0x08003C6E),
               (0x08003CF6, 0x08003C6E), (0x08003D04, 0x0802141C),
               (0x08003D1C, 0x0802141C)]},
    {"address": 0x0800AC10,
     "name": "Character_SetLevel",
     "registers": {0: 0x02000000},
     "memory": [(0x02000000, 4, 2), (0x02000004, 4, 0), (0x02000008, 4, 3),
                (0x03000EAC, 4, 0)],
     "stubs": {0x08004214: {0: 1}},
     "return": 0x3000E9C,
     "writes": [(0x02000000, 4, 1), (0x02000000, 4, 0)],
     "calls": [(0x0800AC3E, 0x08004214), (0x0800AC4E, 0x08003CA0),
               (0x0800AC56, 0x08004276)]},
    {"address": 0x0800379C,
     "name": "Character_DrawStatusPage",
     "registers": {0: 0x02000000, 1: 0},
     "memory": [(0x02000158, 4, 0), (0x03000E90, 1, 0), (0x03000E9C, 2, 0x0A00),
                (0x03000E9E, 2, 0x0A00), (0x03000EA0, 2, 7), (0x03000EA2, 2, 7),
                (0x03000EA4, 1, 0), (0x03000EA6, 2, 0x100), (0x03000EA8, 2, 0x200),
                (0x03000EAA, 2, 0x300), (0x03000EAC, 4, 60)],
     "return": 0x3007EA4,
     "writes": [],
     "calls": [(0x080037C8, 0x08020E5C), (0x080037D2, 0x08020E5C),
               (0x080037DE, 0x08020E5C), (0x08003804, 0x0801F394),
               (0x0800380A, 0x08004214), (0x08003834, 0x08021F18),
               (0x08003840, 0x0801F6D8), (0x08003852, 0x0801F636),
               (0x0800386C, 0x0801F6D8), (0x0800387C, 0x08021F30),
               (0x08003898, 0x0802130A), (0x080038AA, 0x0801F636),
               (0x080038C4, 0x0801F6D8), (0x080038D4, 0x08021F30),
               (0x080038EC, 0x0802130A), (0x080038F4, 0x0801F08C),
               (0x080038FE, 0x0801F394), (0x08003940, 0x0801F636),
               (0x08003952, 0x0801F6D8), (0x0800397E, 0x08021188),
               (0x08003990, 0x0801F636), (0x080039A2, 0x0801F6D8),
               (0x080039CA, 0x08021188), (0x080039DC, 0x0801F636),
               (0x080039EE, 0x0801F6D8), (0x08003A18, 0x08021188),
               (0x08003A1E, 0x0801F110), (0x08003A30, 0x0801F6D8),
               (0x08003A40, 0x08004230), (0x08003A4A, 0x0801F6D8),
               (0x08003A68, 0x0801F636), (0x08003A7C, 0x0801F636),
               (0x08003A8E, 0x0800BDCC), (0x08003A94, 0x0801F394),
               (0x08003AA0, 0x080211C8), (0x08003AC2, 0x0801F508),
               (0x08003ACC, 0x0801F508), (0x08003AD4, 0x080236B4),
               (0x08003ADE, 0x080236B4), (0x08003AE6, 0x08020EAA),
               (0x08003AEE, 0x08020EAA), (0x08003AF6, 0x08020EAA)]},
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
        if "calls_len" in case:
            assert len(result["calls"]) == case["calls_len"], case["name"]
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


def test_the_sixth_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_SIX)


def test_the_seventh_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_SEVEN)


def test_the_eighth_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_EIGHT)


def test_the_ninth_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_NINE)


def test_the_tenth_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_TEN)


def test_the_eleventh_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_ELEVEN)


def test_the_twelfth_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_TWELVE)


def test_the_thirteenth_batch_asserts_the_recorded_body_effects():
    check_cases(CASES_THIRTEEN)


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


