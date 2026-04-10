# Build WordBombGUI.exe and WordBombCLI.exe into dist\
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Installing runtime + build dependencies..."
python -m pip install -r requirements.txt -r requirements-build.txt

Write-Host "`nBuilding WordBombGUI.exe ..."
pyinstaller --noconfirm --clean word-bomb-gui.spec

Write-Host "`nBuilding WordBombCLI.exe ..."
pyinstaller --noconfirm word-bomb-cli.spec

Write-Host "`nDone:"
Write-Host "  $PSScriptRoot\dist\WordBombGUI.exe"
Write-Host "  $PSScriptRoot\dist\WordBombCLI.exe"
