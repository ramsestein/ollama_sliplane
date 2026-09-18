@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro Python en el PATH.
    echo Instala Python 3.9+ con torch, transformers y cryptography.
    pause
    exit /b 1
)

python client_app.py
pause
