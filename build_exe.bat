@echo off
setlocal
cd /d "%~dp0"

echo Installing runtime + build dependencies...
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

echo.
echo Building WordBombGUI.exe ...
pyinstaller --noconfirm --clean word-bomb-gui.spec
if errorlevel 1 exit /b 1

echo.
echo Building WordBombCLI.exe ...
pyinstaller --noconfirm word-bomb-cli.spec
if errorlevel 1 exit /b 1

echo.
echo Done. Outputs:
echo   %~dp0dist\WordBombGUI.exe
echo   %~dp0dist\WordBombCLI.exe
endlocal
