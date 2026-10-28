# One-time setup for Steam Card Bot on Windows 11.
# Run from the extracted bot folder. This script does not start the bot or send trades.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

Write-Host ''
Write-Host 'Steam Card Bot — первичная настройка' -ForegroundColor Cyan
Write-Host 'Проверяю Python и устанавливаю зависимости. Торговые операции не запускаются.' -ForegroundColor Gray
Write-Host ''

$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host '[ОШИБКА] Не найден Python Launcher (py.exe).' -ForegroundColor Red
    Write-Host 'Установи Python 3.11 или новее с официального сайта python.org и отметь Python Launcher.'
    exit 2
}

$versionText = (& py -3 --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ОШИБКА] Python 3 не найден через команду py -3.' -ForegroundColor Red
    exit 2
}
if ($versionText -notmatch 'Python\s+(\d+)\.(\d+)') {
    Write-Host "[ОШИБКА] Не удалось определить версию Python: $versionText" -ForegroundColor Red
    exit 2
}
$pythonMajor = [int]$Matches[1]
$pythonMinor = [int]$Matches[2]
if (($pythonMajor -lt 3) -or (($pythonMajor -eq 3) -and ($pythonMinor -lt 11))) {
    Write-Host "[ОШИБКА] Требуется Python 3.11 или новее; найдено: $versionText" -ForegroundColor Red
    exit 2
}
Write-Host "[OK] $versionText"

Write-Host 'Устанавливаю библиотеки из requirements.txt...'
& py -3 -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Не удалось обновить pip.' }
& py -3 -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости.' }

function Read-RequiredValue([string]$Label, [string]$Name, [bool]$Secret = $false) {
    $current = [Environment]::GetEnvironmentVariable($Name, 'User')
    if (-not [string]::IsNullOrWhiteSpace($current)) {
        $answer = Read-Host "$Label уже настроен. Оставить текущий? Введи Д чтобы заменить, Enter чтобы оставить"
        if ($answer.Trim().ToLowerInvariant() -notin @('д','да','y','yes')) { return $current }
    }

    while ($true) {
        if ($Secret) {
            $secure = Read-Host $Label -AsSecureString
            $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try { $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        } else {
            $value = Read-Host $Label
        }
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            [Environment]::SetEnvironmentVariable($Name, $value.Trim(), 'User')
            return $value.Trim()
        }
        Write-Host 'Поле не может быть пустым.' -ForegroundColor Yellow
    }
}

Write-Host ''
Write-Host 'Сохраняем несекретные настройки и Telegram-токен в переменных среды текущего пользователя Windows.' -ForegroundColor Cyan
Write-Host 'Пароль Steam не сохраняется: при каждом запуске его запросит run_bot.ps1 скрытым вводом.'
[void](Read-RequiredValue 'Telegram Bot Token (из BotFather)' 'TG_TOKEN' $true)
$steamId = Read-RequiredValue 'SteamID64 (17 цифр)' 'STEAM_ID'
if ($steamId -notmatch '^\d{17}
) {
    Write-Host '[ОШИБКА] SteamID64 должен состоять из 17 цифр. Перезапусти настройку и введи корректный ID.' -ForegroundColor Red
    exit 2
}
[void](Read-RequiredValue 'Имя аккаунта Steam для входа' 'STEAM_LOGIN')
[Environment]::SetEnvironmentVariable('STEAM_PASSWORD', $null, 'User')

Write-Host ''
Write-Host '[OK] Зависимости установлены, настройки сохранены.' -ForegroundColor Green
Write-Host 'Следующий шаг: настрой ASF и FunPay, затем запусти start.bat.' -ForegroundColor Yellow
Write-Host 'Пароль Steam запрашивается только на время процесса; настройка не проверяет Steam-вход и не отправляет предложения обмена.'
