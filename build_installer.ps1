# Build the Windows installer for WordBombGUI.exe and WordBombCLI.exe.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$distDir = Join-Path $PSScriptRoot "dist"
$installerScript = Join-Path $PSScriptRoot "word-bomb-installer.iss"
$outputFile = Join-Path $distDir "WordBombTool-Setup.exe"

if (-not (Test-Path $distDir)) {
    throw "The dist folder was not found. Build the executables first using build_exe.ps1 or build_exe.bat."
}

$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $compiler) {
    $commonPaths = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            $compiler = New-Object psobject -Property @{ Source = $path }
            break
        }
    }
}
if (-not $compiler) {
    throw "Inno Setup compiler 'ISCC.exe' was not found on PATH or in common install locations. Install Inno Setup 6 and rerun."
}

Write-Host "Building installer using compiler: $($compiler.Source)"
& $compiler.Source "/Qp" $installerScript

if (-not (Test-Path $outputFile)) {
    throw "Installer build failed. Check Inno Setup output for details."
}

Write-Host "Installer created:"
Write-Host "  $outputFile"
