@echo off
setlocal
chcp 65001 >nul
set "BOT_DIR=%~dp0"

title Steam Card Bot - запуск

echo ===================================================
echo Steam Card Bot - переносимый запуск
echo Папка бота: "%BOT_DIR%"
echo ===================================================

rem Не запускаем старый update_bot.ps1: он привязан к C:\CardBot и ветке main.
rem Путь к ASF можно задать переменной пользователя CARD_BOT_ASF_DIR.
if not defined CARD_BOT_ASF_DIR set "CARD_BOT_ASF_DIR=%BOT_DIR%ASF-win-x64 (1)"

if exist "%CARD_BOT_ASF_DIR%\ArchiSteamFarm.exe" (
    tasklist /FI "IMAGENAME eq ArchiSteamFarm.exe" 2>NUL | find /I "ArchiSteamFarm.exe" >NUL
    if errorlevel 1 (
        echo [INFO] Запускаю ASF из "%CARD_BOT_ASF_DIR%"
        start "ArchiSteamFarm" /D "%CARD_BOT_ASF_DIR%" "%CARD_BOT_ASF_DIR%\ArchiSteamFarm.exe"
        echo Ожидание запуска ASF...
        timeout /t 10 /nobreak >nul
    ) else (
        echo [OK] ASF уже работает.
    )
) else (
    echo [WARN] ASF не найден в "%CARD_BOT_ASF_DIR%".
    echo [WARN] Бот запустится, но автоматическая выдача через Steam может не работать.
)

:loop
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%BOT_DIR%run_bot.ps1"
if errorlevel 23 (
    echo [INFO] Бот уже запущен; повторный запуск пропущен.
    exit /b 0
)
echo Бот завершился. Повторный запуск через 5 секунд...
timeout /t 5 /nobreak >nul
goto loop
