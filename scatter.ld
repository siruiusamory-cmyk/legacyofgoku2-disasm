ROM_LOAD 0x08000000 {
	ROM_START 0x08000000
	{
		buu.o (RomHeader)
	}
	ROM_CRT0 0x080000c0
	{
		buu.o (Init)
	}
	ROM_REMAINDER 0x08000100
	{
		buu.o (Remainder)
	}
}
