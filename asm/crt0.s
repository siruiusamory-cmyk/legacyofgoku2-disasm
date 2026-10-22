	AREA	Init, CODE, READONLY
		CODE32

		mov		r0, #0x92
		msr		cpsr_c, r0
		ldr		sp, [pc, #0x64]
		mov		r0, #0x1f
		msr		cpsr_c, r0
		ldr		sp, [pc, #0x5c]

		mov		r0, #0x4000000
		ldr		r1, [pc, #0x58]
		str		r1, [r0, #0x204]

		mov		r1, #0x0
		stmdb	sp!, {r1}

		str		sp, [r0, #0xd4]
		ldr		r1, [pc, #0x48]
		str		r1, [r0, #0xd8]
		ldr		r1, [pc, #0x44]
		movs	r1, r1, lsr #2

	END
