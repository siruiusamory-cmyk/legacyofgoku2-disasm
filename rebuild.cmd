@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
if "%ADS%"=="" set "ADS=%~dp0..\toolchains\ads12-build805"
set "PATH=%ADS%\Bin;%PATH%"
set "ARMHOME=%ADS%"
set "ARMINC=%ADS%\Include"
set "ARMLIB=%ADS%\Lib"
cd /d "%ROOT%"
if not exist build mkdir build
echo === code generator ===
python tools\code\emit_code.py --write --out build\code
echo code_generate_exit=%ERRORLEVEL%
echo === function boundaries ===
python tools\code\function_bounds.py --check
echo function_bounds_exit=%ERRORLEVEL%
echo === incbin slices ===
call tools\incbin.bat baserom.gba 0x0 0xc0
echo incbin_header_exit=%ERRORLEVEL%
echo === map records ===
python tools\maprecords\maprecords.py --write
echo map_records_exit=%ERRORLEVEL%
echo === sprite records ===
python tools\sprites\sprites.py --write
echo sprite_records_exit=%ERRORLEVEL%
echo === text records ===
python tools\text\text_rows.py --write
echo text_records_exit=%ERRORLEVEL%
echo === table records ===
python tools\records\table_086f6d8c.py --write
echo table_records_exit=%ERRORLEVEL%
echo === opcode rows ===
python tools\records\opcode_rows.py --write
echo opcode_rows_exit=%ERRORLEVEL%
echo === address runs ===
python tools\addr\addr_runs.py --write
echo address_runs_exit=%ERRORLEVEL%
echo === transform slots ===
python tools\records\transform_slots.py --write
echo transform_slots_exit=%ERRORLEVEL%
echo === compressor ===
if not exist "%ROOT%\tools\compress\compress.exe" call "%ROOT%\tools\compress\build.cmd"
if errorlevel 1 exit /b 1
python tools\compress\generate_containers.py
echo container_generate_exit=%ERRORLEVEL%
echo === building asm files ===
armasm asm\buu.s -o build/buu.o
echo armasm_buu_exit=%ERRORLEVEL%
echo === linking and converting ===
armlink build/buu.o -noremove -scatter scatter.ld -map -symbols -o build/log2.axf 2> build\log2.map
echo armlink_exit=%ERRORLEVEL%
if errorlevel 1 findstr /i /c:"error:" build\log2.map
fromelf build/log2.axf -bin -o build\ROM_START
echo fromelf_exit=%ERRORLEVEL%
dir /b build\ROM_START
echo DONE

