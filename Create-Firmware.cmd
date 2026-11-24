@echo off
cd /d "%~dp0"
PatchTool.exe prepare
if errorlevel 1 goto failed
echo Firmware files are ready in output. Read docs\UPDATING.ko.md.
pause
exit /b 0
:failed
echo Preparation stopped. Nothing was flashed.
pause
exit /b 1
