@echo off
:: =============================================================
:: FAMILY COMMAND CENTER V3.0 - AUTOMATED DEPLOYMENT SCRIPT (SAFE)
:: =============================================================
echo Packaging deployment bundle locally...

:: 1. Package the files into a single archive, excluding database and media assets
if exist deploy.tar del /f /q deploy.tar
tar --exclude="database.db" --exclude="photos.json" --exclude="calendar.json" --exclude="static/photos" --exclude="static/media" -cf deploy.tar server.py static

if not exist deploy.tar (
    echo [!] Error: Failed to package deployment bundle using tar.
    pause
    exit /b 1
)

echo.
echo [!] PASSWORD PROMPT 1: Uploading deployment archive to Bosgame Mini PC...
scp deploy.tar senyog@192.168.1.211:/home/senyog/

echo.
echo [!] PASSWORD PROMPT 2 (Double-prompt for sudo): Extracting assets and restarting server...
ssh -t senyog@192.168.1.211 "chmod -R u+w /home/senyog/family-dashboard 2>/dev/null; cd /home/senyog/family-dashboard && tar -xf /home/senyog/deploy.tar && rm /home/senyog/deploy.tar && chcon -R -t httpd_sys_content_t photos photos.json 2>/dev/null; sudo systemctl restart family-dashboard.service"

:: Clean up local archive
if exist deploy.tar del /f /q deploy.tar

echo =============================================================
echo SUCCESS: Deployment complete! Your live data is perfectly safe.
echo =============================================================
pause