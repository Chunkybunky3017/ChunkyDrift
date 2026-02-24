@echo off
setlocal
cd /d "%~dp0"

set "CONDA_EXE=C:/Users/jmcor/miniconda3/Scripts/conda.exe"
set "CONDA_PREFIX_PATH=C:\Users\jmcor\miniconda3"

if not exist "%CONDA_EXE%" (
  echo Could not find conda executable at:
  echo %CONDA_EXE%
  echo.
  echo Update CONDA_EXE in run_web_server.bat to your actual path.
  pause
  exit /b 1
)

echo Starting web multiplayer server on http://127.0.0.1:8000
echo Press Ctrl+C to stop.
echo.
echo Checking Python web dependencies...
"%CONDA_EXE%" run -p "%CONDA_PREFIX_PATH%" --no-capture-output python -c "import fastapi, uvicorn, websockets" >nul 2>&1
if errorlevel 1 (
  echo Installing/updating required packages from web_multiplayer\requirements.txt...
  "%CONDA_EXE%" run -p "%CONDA_PREFIX_PATH%" --no-capture-output python -m pip install -r web_multiplayer/requirements.txt
  if errorlevel 1 (
    echo.
    echo Failed to install dependencies.
    pause
    exit /b 1
  )
  echo.
)

"%CONDA_EXE%" run -p "%CONDA_PREFIX_PATH%" --no-capture-output python -m uvicorn web_multiplayer.server:app --host 127.0.0.1 --port 8000

if errorlevel 1 (
  echo.
  echo Server exited with an error.
  pause
)
