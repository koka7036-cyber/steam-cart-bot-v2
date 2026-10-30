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
        $requiredNames = @('TG_TOKEN', 'STEAM_ID', 'STEAM_LOGIN')
        $missing = @()

        foreach ($name in $requiredNames) {
            $value = [Environment]::GetEnvironmentVariable($name, 'User')
            if ([string]::IsNullOrWhiteSpace($value)) {
                $missing += $name
            } else {
                [Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }

        if ($missing.Count -gt 0) {
            Write-Host ('[ERROR] Missing required Windows environment variables: ' + ($missing -join ', ')) -ForegroundColor Red
            $exitCode = 2
        } elseif (-not (Get-Command py -ErrorAction SilentlyContinue)) {
            Write-Host '[ERROR] Python Launcher py.exe was not found.' -ForegroundColor Red
            $exitCode = 2
        } else {
            [Environment]::SetEnvironmentVariable('STEAM_PASSWORD', '', 'Process')
            $optionalNames = @('PLAYEROK_TOKEN', 'PLAYEROK_USER_AGENT', 'PLAYEROK_ITEM_1_SET_ID', 'PLAYEROK_ITEM_5_SET_ID')
            foreach ($name in $optionalNames) {
                $value = [Environment]::GetEnvironmentVariable($name, 'User')
                if (-not [string]::IsNullOrWhiteSpace($value)) {
                    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
                }
            }

            # Bot-launched checks and updates must never prompt for credentials.
            # The first interactive start.bat run registers the GitHub token once.
            [Environment]::SetEnvironmentVariable('CARD_BOT_NONINTERACTIVE', '1', 'Process')
            Set-Location -LiteralPath $PSScriptRoot

            do {
                & py -3 (Join-Path $PSScriptRoot 'bot.py')
                $exitCode = $LASTEXITCODE

                if ($exitCode -eq 43) {
                    Write-Host '[INFO] Telegram requested an update. Stopping bot process is complete.' -ForegroundColor Cyan
                    $requestFile = Join-Path $PSScriptRoot '.bot_update_expected_sha.txt'
                    $expectedSha = ''

                    if (Test-Path -LiteralPath $requestFile -PathType Leaf) {
                        $expectedSha = (Get-Content -LiteralPath $requestFile -Raw -ErrorAction SilentlyContinue).Trim()
                    }

                    if ($expectedSha -match '^[0-9a-f]{40}$') {
                        $updateScript = Join-Path $PSScriptRoot 'update_bot.ps1'
                        Write-Host ('[INFO] Applying verified GitHub commit ' + $expectedSha) -ForegroundColor Cyan
                        & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $updateScript -WaitForBot -ExpectedSha $expectedSha
                        $updateExitCode = $LASTEXITCODE

                        if ($updateExitCode -ne 0) {
                            Write-Host '[WARN] Update failed. The previous installed version will be started again.' -ForegroundColor Yellow
                        }
                    } else {
                        Write-Host '[WARN] Update request SHA is missing or invalid. The current version will be restarted.' -ForegroundColor Yellow
                    }

                    if (Test-Path -LiteralPath $requestFile -PathType Leaf) {
                        Remove-Item -LiteralPath $requestFile -Force -ErrorAction SilentlyContinue
                    }

                    $exitCode = 42
                    Start-Sleep -Seconds 2
                } elseif ($exitCode -eq 42) {
                    Write-Host '[INFO] Telegram requested a normal restart.' -ForegroundColor Cyan
                    Start-Sleep -Seconds 2
                }
            } while ($exitCode -eq 42)
        }
    } else {
        Write-Output 'Bot already running; duplicate launch skipped.'
    }
} finally {
    if ($held) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}

exit $exitCode
