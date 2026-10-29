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

REM Avoid CMD parser errors by keeping complex discovery logic in PowerShell.
set "ASF_EXE="
set "CACHE=%~dp0.asf_path.txt"
if defined CARD_BOT_ASF_DIR if exist "%CARD_BOT_ASF_DIR%\ArchiSteamFarm.exe" set "ASF_EXE=%CARD_BOT_ASF_DIR%\ArchiSteamFarm.exe"
if not defined ASF_EXE if exist "%CACHE%" set /p ASF_EXE=<"%CACHE%"
if defined ASF_EXE if not exist "%ASF_EXE%" set "ASF_EXE="

if not defined ASF_EXE (
  echo Searching for ArchiSteamFarm.exe...
  >> "%LOG%" echo [%date% %time%] Searching for ASF with PowerShell.
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $roots=@([Environment]::GetFolderPath('Desktop'),(Join-Path $env:USERPROFILE 'Downloads'),$env:OneDrive,'C:\CardBot',(Get-Location).Path); $roots=$roots|Where-Object{$_ -and (Test-Path -LiteralPath $_)}|Select-Object -Unique; foreach($root in $roots){$hit=Get-ChildItem -LiteralPath $root -Filter 'ArchiSteamFarm.exe' -File -Recurse -ErrorAction SilentlyContinue|Select-Object -First 1; if($hit){[Console]::Write($hit.FullName); exit 0}}; exit 1" > "%TEMP%\cardbot_asf_path.txt"
  if exist "%TEMP%\cardbot_asf_path.txt" set /p ASF_EXE=<"%TEMP%\cardbot_asf_path.txt"
  del "%TEMP%\cardbot_asf_path.txt" >nul 2>&1
)

if not defined ASF_EXE (
  echo ASF was not found automatically.
  echo Select ArchiSteamFarm.exe, or cancel to continue without ASF.
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select ArchiSteamFarm.exe (Cancel to continue without ASF)'; $d.Filter='ArchiSteamFarm.exe|ArchiSteamFarm.exe|Executable files (*.exe)|*.exe'; if($d.ShowDialog() -eq 'OK'){[Console]::Write($d.FileName)}" > "%TEMP%\cardbot_asf_path.txt"
  if exist "%TEMP%\cardbot_asf_path.txt" set /p ASF_EXE=<"%TEMP%\cardbot_asf_path.txt"
  del "%TEMP%\cardbot_asf_path.txt" >nul 2>&1
)

if defined ASF_EXE if exist "%ASF_EXE%" (
  echo [INFO] ASF found: "%ASF_EXE%"
  >> "%LOG%" echo [%date% %time%] ASF found: "%ASF_EXE%"
  >"%CACHE%" echo %ASF_EXE%
  tasklist /FI "IMAGENAME eq ArchiSteamFarm.exe" 2>NUL | find /I "ArchiSteamFarm.exe" >NUL
  if errorlevel 1 (
    for %%I in ("%ASF_EXE%") do start "ArchiSteamFarm" /D "%%~dpI" "%ASF_EXE%"
    timeout /t 2 /nobreak >nul
  ) else echo [INFO] ASF is already running.
) else (
  echo [WARN] ASF not found/selected. Continuing without ASF.
  >> "%LOG%" echo [%date% %time%] ASF not found/selected; bot-only startup.
)

if not exist "%~dp0run_bot.ps1" (
  echo [ERROR] run_bot.ps1 not found beside start.bat.
  >> "%LOG%" echo [%date% %time%] ERROR: run_bot.ps1 missing.
  pause
  exit /b 2
)
echo Starting Telegram bot...
>> "%LOG%" echo [%date% %time%] Starting run_bot.ps1
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0run_bot.ps1"
echo.
echo Launcher finished. Log: "%LOG%"
pause
endlocal
