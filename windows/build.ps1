$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectDir
try {
    python -m PyInstaller --noconfirm --clean --onefile --console --name PatchTool --add-data 'patches;patches' --hidden-import windows.boot_identity patcher.py
    if ($LASTEXITCODE -ne 0) { throw 'PatchTool build failed' }
    $compilerPath = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
    & $compilerPath /nologo /target:exe /platform:x86 /optimize+ /r:System.Management.dll /out:dist\FlashTool.exe windows\FlashTool.cs
    if ($LASTEXITCODE -ne 0) { throw 'FlashTool build failed' }
} finally { Pop-Location }
