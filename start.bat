@echo off
rem OW Tracker: double-click to start. The first run sets everything up (a few minutes).
setlocal
cd /d "%~dp0"

if exist venv\Scripts\python.exe goto run

echo First run: setting up OW Tracker. This takes a few minutes and only happens once.
echo.

rem Find Python 3.10 or newer. "py" is the launcher python.org installs.
set "PY="
for %%V in (3.12 3.13 3.11 3.10 3.14 3.15) do (
  if not defined PY (
    py -%%V -c "pass" >nul 2>nul && (set "PY=py -%%V")
  )
)
if not defined PY (
  python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && (set "PY=python")
)
if not defined PY (
  echo Python 3.10 or newer wasn't found.
  echo Install it from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 1
)

%PY% -m venv venv || goto failed
venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt || goto failed
echo.
echo Setup done.

:run
echo Starting OW Tracker at http://localhost:8000  (close this window to stop it)
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
venv\Scripts\python.exe main.py
pause
exit /b

:failed
echo.
echo Setup failed. Delete the "venv" folder and run this again; if it keeps failing,
echo send the messages above to whoever shared OW Tracker with you.
pause
exit /b 1
