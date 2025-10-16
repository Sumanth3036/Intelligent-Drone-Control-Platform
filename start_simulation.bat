@echo off

echo Starting WebSocket Server...

cd /d "C:\Users\suman\OneDrive\Documents\webots_projects\websocket_server"

start "WebSocket Server" cmd /k "python websocket_server.py"

echo Waiting 3 seconds for server to start...

timeout /t 3 /nobreak > nul

echo Opening Dashboard...

cd /d "C:\Users\suman\OneDrive\Documents\webots_projects\dashboard"

start "Dashboard" msedge.exe drone_dashboard.html

echo.
echo =====================================
echo All components started successfully!
echo =====================================
echo.
echo 1. WebSocket Server is running
echo 2. Dashboard is open in your browser
echo 3. You can now start your Webots simulation
echo.
echo Press any key to close this window...

pause > nul