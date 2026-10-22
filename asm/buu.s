	INCLUDE	registers.s
	INCLUDE	memory.s

	AREA	RomHeader, CODE, READONLY
		INCBIN	baserom.gba_0x0_0xc0.extracted

	INCLUDE	crt0.s

	INCLUDE	remainder.s

	END
