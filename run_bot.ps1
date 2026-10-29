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
            $securePassword = Read-Host 'Пароль Steam (ввод скрыт; не сохраняется в переменных пользователя)' -AsSecureString
            $passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
            try {
                $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
                if ([string]::IsNullOrWhiteSpace($plainPassword)) {
                    Write-Host '[ERROR] Пароль Steam не может быть пустым.' -ForegroundColor Red
                    $exitCode = 2
                } else {
                    [Environment]::SetEnvironmentVariable('STEAM_PASSWORD', $plainPassword, 'Process')
                }
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
                $securePassword.Dispose()
            }
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
                & py -3 (Join-Path $PSScriptRoot 'bot.py')
                $exitCode = $LASTEXITCODE
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
