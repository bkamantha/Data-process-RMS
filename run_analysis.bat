@echo off
cd /d "%~dp0"
if "%~1"=="" (
  python run_analysis.py --all-periods
) else (
  python run_analysis.py %*
)
