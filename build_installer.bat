@echo off
setlocal
cd /d "%~dp0"

if not exist dist (
  echo ERROR: dist folder not found. Build the executables first with build_exe.bat
  exit /b 1
)

where ISCC.exe >nul 2>&1
if errorlevel 1 (
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  ) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
  ) else (
    echo ERROR: ISCC.exe not found. Install Inno Setup 6 and ensure it is on PATH.
    exit /b 1
  )
)

echo Building installer...
if defined ISCC_PATH (
  "%ISCC_PATH%" /Qp word-bomb-installer.iss
) else (
  ISCC.exe /Qp word-bomb-installer.iss
)
if errorlevel 1 exit /b 1

echo.
echo Done. Output:
echo   %~dp0dist\WordBombTool-Setup.exe
endlocal
