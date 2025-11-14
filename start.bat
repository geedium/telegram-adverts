@echo off
REM === Quick Start Script ===
REM Mount the virtual environment and run main.py

echo Activating virtual environment...
call .venv\Scripts\activate

echo Starting main.py...
python main.py

echo.
echo ==========================
echo Program finished.
pause
