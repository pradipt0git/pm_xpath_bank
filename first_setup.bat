@echo off
echo ========================================
echo XPath Collector - First Time Setup
echo ========================================
echo.

REM Get the current directory
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo Current directory: %PROJECT_DIR%
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.7 or higher and try again
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
if exist ".venv" (
    echo Virtual environment already exists. Skipping creation.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
)
echo.

echo [2/4] Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo.

echo [3/4] Installing required packages...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install packages
    pause
    exit /b 1
)
echo Packages installed successfully.
echo.

echo [4/4] Updating batch files with correct paths...

REM Update run_web.bat
(
echo @echo off
echo cd /d "%PROJECT_DIR%"
echo "%PROJECT_DIR%.venv\Scripts\python.exe" web_app.py
echo pause
) > run_web.bat
echo Updated run_web.bat

REM Update run.bat
(
echo @echo off
echo cd /d "%PROJECT_DIR%"
echo "%PROJECT_DIR%.venv\Scripts\python.exe" main.py
echo pause
) > run.bat
echo Updated run.bat

echo.
echo ========================================
echo Setup completed successfully!
echo ========================================
echo.
echo You can now run the application using:
echo   - run_web.bat (to start the web UI)
echo   - run.bat (to start capture directly)
echo.
pause
