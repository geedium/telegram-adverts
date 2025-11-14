@echo off
REM === Quick Start Script ===
REM Mount the virtual environment and run main.py

echo Activating virtual environment...
call .venv\Scripts\activate

echo Installing dependencies
pip install -r requirements.txt

echo.
echo ==========================
echo Program finished.
pause
