@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    echo Please run install_and_run.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
endlocal