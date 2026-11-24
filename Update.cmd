@echo off
cd /d "%~dp0"
if not exist output\controller-enhanced.dat goto prepare
if not exist vendor-runtime\8BitDoFirmwareUpdaterTools.dll goto prepare
goto flash
:prepare
PatchTool.exe prepare
if errorlevel 1 goto failed
:flash
FlashTool.exe
set "flashResult=%errorlevel%"
pause
exit /b %flashResult%
:failed
echo Preparation stopped. Nothing was flashed.
pause
exit /b 1
