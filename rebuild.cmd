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
