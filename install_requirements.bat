@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
echo.
echo Dependencies installed. Run:
echo   python run_analysis.py --period 1_month
echo   python -m streamlit run app.py
pause
