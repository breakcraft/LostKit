@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR%"=="" set "SCRIPT_DIR=."
set "VENV_PY=%SCRIPT_DIR%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Virtual environment not found at "%SCRIPT_DIR%\.venv".
    echo Run "py -3.11 -m venv .venv" from the project root first.
    endlocal & exit /b 1
)

pushd "%SCRIPT_DIR%"
echo Launching LostKit with "%VENV_PY%"
call "%VENV_PY%" main.py %*
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
    echo LostKit exited with code %EXIT_CODE%.
)

endlocal & exit /b %EXIT_CODE%
