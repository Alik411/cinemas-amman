@echo off
echo ============================================
echo  CineAmman Scraper — Setup
echo ============================================

echo.
echo [1/4] Creating Python virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    echo Make sure Python is installed and added to PATH.
    pause
    exit /b 1
)

echo.
echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [3/4] Installing Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo [4/4] Installing Playwright browser (Chromium)...
playwright install chromium
if errorlevel 1 (
    echo ERROR: Playwright browser install failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Setup complete!
echo  To run the scraper:
echo    venv\Scripts\activate
echo    python main.py
echo ============================================
pause
