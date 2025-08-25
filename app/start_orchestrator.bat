@echo off
REM Script de inicialização do Stream Orchestrator para Windows

cd /d "D:\dataradio\finger_vpn\app"

REM Ativar ambiente virtual se existir
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Executar orquestrador
python orchestrator.py

pause
