@echo off
echo ===================================================
echo             STARTING APEX SHOP SERVER
echo ===================================================
echo.
echo Launching your browser at http://127.0.0.1:5000 ...
start http://127.0.0.1:5000
echo.
echo Starting Flask web server...
python App.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Failed to start Python server.
    echo Make sure Python is installed and in your PATH.
    echo.
    pause
)
