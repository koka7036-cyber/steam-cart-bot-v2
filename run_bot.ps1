$ErrorActionPreference = 'Stop'
$mutex = New-Object System.Threading.Mutex($false, 'Local\CardBotBotSingleInstance')
$held = $false
$exitCode = 23

try {
    try {
        $held = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $held = $true
    }

    if ($held) {
        $exitCode = 0
        $names = @('TG_TOKEN', 'STEAM_ID', 'STEAM_LOGIN')
        $missing = @()
        foreach ($name in $names) {
            $value = [Environment]::GetEnvironmentVariable($name, 'User')
            if ([string]::IsNullOrWhiteSpace($value)) {
                $missing += $name
            } else {
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }

        if ($missing.Count -gt 0) {
            Write-Host ("[ERROR] Не настроены обязательные переменные Windows: " + ($missing -join ', ') + ". Настрой их перед запуском.") -ForegroundColor Red
            $exitCode = 2
        } elseif (-not (Get-Command py -ErrorAction SilentlyContinue)) {
            Write-Host "[ERROR] Python Launcher (py.exe) не найден. Установи Python 3.11+ с python.org и включи Python Launcher." -ForegroundColor Red
            $exitCode = 2
        } else {
            # Steam password is intentionally not requested in the console.
            # Authenticate once from the admin-only Telegram menu; the local session is reused on restart.
            [Environment]::SetEnvironmentVariable('STEAM_PASSWORD', '', 'Process')
            Write-Host '[INFO] Steam: используется сохранённая сессия, если она ещё действительна.' -ForegroundColor Cyan
            Write-Host '[INFO] Если потребуется новый вход, открой Telegram → Настройки → Авторизация Steam.' -ForegroundColor Yellow
            # Playerok settings are optional. A missing token keeps the monitor disabled.
            $optionalNames = @('PLAYEROK_TOKEN', 'PLAYEROK_USER_AGENT', 'PLAYEROK_ITEM_1_SET_ID', 'PLAYEROK_ITEM_5_SET_ID')
            foreach ($name in $optionalNames) {
                $value = [Environment]::GetEnvironmentVariable($name, 'User')
                if (-not [string]::IsNullOrWhiteSpace($value)) {
                    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
                }
            }

            if ($exitCode -ne 2) {
                Set-Location -LiteralPath $PSScriptRoot
                do {
                    & py -3 (Join-Path $PSScriptRoot 'bot.py')
                    $exitCode = $LASTEXITCODE
                    if ($exitCode -eq 42) {
                        Write-Host '[INFO] Telegram requested a restart. Relaunching bot...' -ForegroundColor Cyan
                        Start-Sleep -Seconds 2
                    }
                } while ($exitCode -eq 42)
            }
        }
    } else {
        Write-Output 'Bot already running; duplicate launch skipped.'
    }
} finally {
    if ($held) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}

exit $exitCode
