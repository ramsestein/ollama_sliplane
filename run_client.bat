@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Install Python 3.9+ with torch, transformers and cryptography.
    pause
    exit /b 1
)

python -m src.client_app
pause
