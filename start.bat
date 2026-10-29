@echo off
setlocal
chcp 65001 >nul
title Steam Cards Bot Launcher
cd /d "%~dp0"

echo ==================================================
echo Steam Cards Bot Launcher
echo ==================================================
echo.

REM ASF is optional for starting the Telegram bot.
set "ASF_EXE="
set "CACHE=%~dp0.asf_path.txt"
if exist "%CACHE%" set /p ASF_EXE=<"%CACHE%"
if defined ASF_EXE if not exist "%ASF_EXE%" set "ASF_EXE="

if not defined ASF_EXE (
    for %%P in (
        "%~dp0ArchiSteamFarm.exe"
        "%~dp0ASF\ArchiSteamFarm.exe"
        "%~dp0ASF-win-x64\ArchiSteamFarm.exe"
        "%~dp0ASF-win-x64 (1)\ArchiSteamFarm.exe"
        "C:\CardBot\ASF\ArchiSteamFarm.exe"
        "C:\CardBot\ASF-win-x64\ArchiSteamFarm.exe"
        "C:\CardBot\ASF-win-x64 (1)\ArchiSteamFarm.exe"
    ) do (
        if exist "%%~P" (
            set "ASF_EXE=%%~P"
            goto :asf_found
        )
    )
)

:asf_found
if not defined ASF_EXE (
    echo ASF path was not found automatically.
    echo Select ArchiSteamFarm.exe, or cancel to continue without ASF.
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select ArchiSteamFarm.exe (Cancel to continue without ASF)'; $d.Filter='ArchiSteamFarm.exe|ArchiSteamFarm.exe|Executable files (*.exe)|*.exe'; if($d.ShowDialog() -eq 'OK'){Write-Output $d.FileName}" > "%TEMP%\cardbot_asf_path.txt"
    if exist "%TEMP%\cardbot_asf_path.txt" set /p ASF_EXE=<"%TEMP%\cardbot_asf_path.txt"
    del "%TEMP%\cardbot_asf_path.txt" >nul 2>&1
)

if defined ASF_EXE (
    if exist "%ASF_EXE%" (
        echo [INFO] ASF: "%ASF_EXE%"
        tasklist /FI "IMAGENAME eq ArchiSteamFarm.exe" 2>NUL | find /I "ArchiSteamFarm.exe" >NUL
        if errorlevel 1 start "ArchiSteamFarm" "%ASF_EXE%"
        >"%CACHE%" echo %ASF_EXE%
    ) else (
        echo [WARN] ASF path is invalid. Continuing without ASF.
    )
) else (
    echo [WARN] ASF not selected. Continuing with Telegram bot only.
)

echo.
echo Starting Telegram bot from:
echo "%~dp0"
if not exist "%~dp0run_bot.ps1" (
    echo [ERROR] run_bot.ps1 not found beside this launcher.
    pause
    exit /b 2
)
start "Steam Cards Telegram Bot" powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0run_bot.ps1"
echo Launch command sent. Check the Telegram bot window for its startup result.
endlocal
