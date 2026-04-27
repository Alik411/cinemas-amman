@echo off
cd /d "C:\Users\DELL\Desktop\Cinemas Amman\scraper"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
call venv\Scripts\activate.bat
python main.py >> "C:\Users\DELL\Desktop\Cinemas Amman\scraper\scraper.log" 2>&1
