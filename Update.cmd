@echo off
cd /d "%~dp0"
PatchTool.exe prepare
if errorlevel 1 goto failed
FlashTool.exe
set "flashResult=%errorlevel%"
pause
exit /b %flashResult%
:failed
echo Preparation stopped. Nothing was flashed.
pause
exit /b 1
