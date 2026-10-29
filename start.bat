@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Steam Cards Bot Launcher
cd /d "%~dp0"
set "LOG=%~dp0launcher_start.log"
> "%LOG%" echo [%date% %time%] Launcher started from "%~dp0"

echo ==================================================
echo Steam Cards Bot Launcher
echo ==================================================
echo.
echo Log: "%LOG%"
echo.

REM ASF is optional. The Telegram bot must still be attempted if ASF is absent.
set "ASF_EXE="
set "CACHE=%~dp0.asf_path.txt"
set "PICK=%TEMP%\cardbot_asf_path.txt"
if defined CARD_BOT_ASF_DIR if exist "%CARD_BOT_ASF_DIR%\ArchiSteamFarm.exe" set "ASF_EXE=%CARD_BOT_ASF_DIR%\ArchiSteamFarm.exe"
if not defined ASF_EXE if exist "%CACHE%" set /p ASF_EXE=<"%CACHE%"
if defined ASF_EXE if not exist "%ASF_EXE%" set "ASF_EXE="

if not defined ASF_EXE (
  for %%P in (
    "%~dp0ArchiSteamFarm.exe"
    "%~dp0ASF\ArchiSteamFarm.exe"
    "%~dp0ASF-win-x64\ArchiSteamFarm.exe"
    "%~dp0ASF-win-x64 (1)\ArchiSteamFarm.exe"
    "%USERPROFILE%\Desktop\ASF-win-x64\ArchiSteamFarm.exe"
    "%USERPROFILE%\Desktop\ASF-win-x64 (1)\ArchiSteamFarm.exe"
    "C:\CardBot\ASF\ArchiSteamFarm.exe"
    "C:\CardBot\ASF-win-x64\ArchiSteamFarm.exe"
    "C:\CardBot\ASF-win-x64 (1)\ArchiSteamFarm.exe"
  ) do if exist "%%~P" (set "ASF_EXE=%%~P" & goto :asf_found)
)

:asf_found
if not defined ASF_EXE (
  echo ASF was not found automatically.
  echo Select ArchiSteamFarm.exe, or cancel to continue without ASF.
  del "%PICK%" >nul 2>&1
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select ArchiSteamFarm.exe (Cancel to continue without ASF)'; $d.Filter='ArchiSteamFarm.exe|ArchiSteamFarm.exe|Executable files (*.exe)|*.exe'; if($d.ShowDialog() -eq 'OK'){[System.IO.File]::WriteAllText($env:TEMP + '\\cardbot_asf_path.txt', $d.FileName, [System.Text.Encoding]::ASCII)}"
  if exist "%PICK%" set /p ASF_EXE=<"%PICK%"
  del "%PICK%" >nul 2>&1
)

if defined ASF_EXE if exist "%ASF_EXE%" (
  echo [INFO] ASF selected: "%ASF_EXE%"
  >> "%LOG%" echo [%date% %time%] ASF selected: "%ASF_EXE%"
  >"%CACHE%" echo %ASF_EXE%
  tasklist /FI "IMAGENAME eq ArchiSteamFarm.exe" 2>NUL | find /I "ArchiSteamFarm.exe" >NUL
  if errorlevel 1 (
    echo [INFO] Starting ASF in its own directory...
    >> "%LOG%" echo [%date% %time%] Starting ASF: "%ASF_EXE%"
    for %%I in ("%ASF_EXE%") do start "ArchiSteamFarm" /D "%%~dpI" "%ASF_EXE%"
    timeout /t 2 /nobreak >nul
  ) else echo [INFO] ASF is already running.
) else (
  echo [WARN] ASF not selected/found. Continuing without ASF.
  >> "%LOG%" echo [%date% %time%] ASF not selected/found; bot-only startup.
)

echo.
if not exist "%~dp0run_bot.ps1" (
  echo [ERROR] run_bot.ps1 not found beside start.bat.
  >> "%LOG%" echo [%date% %time%] ERROR: run_bot.ps1 missing.
  echo See launcher_start.log for details.
  pause
  exit /b 2
)
echo Starting Telegram bot from "%~dp0" ...
>> "%LOG%" echo [%date% %time%] Starting run_bot.ps1
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0run_bot.ps1"
set "BOT_EXIT=%ERRORLEVEL%"
>> "%LOG%" echo [%date% %time%] run_bot.ps1 exited with code %BOT_EXIT%
echo.
echo Launcher ended. Log: "%LOG%"
pause
endlocal
