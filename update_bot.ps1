param(
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$Repo = 'koka7036-cyber/steam-cart-bot-v2'
$Branch = 'sync/local-archive-review-2026-10-29'
$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$Log = Join-Path $Root 'update_bot.log'
$Marker = Join-Path $Root '.bot_update_commit.txt'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Backup = Join-Path $Root ('backups\update_' + $Stamp)
function Log([string]$Message) {
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
    Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
    Write-Host $line
}
try {
    Log "Checking updates for $Repo ($Branch)"
    # Never replace Python files while a bot process is running.
    $botProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and $_.CommandLine -match 'bot\.py'
    })
    if ($botProcesses.Count -gt 0 -and -not $Force) {
        Log 'Bot process appears to be running; update skipped to avoid replacing active files.'
        exit 0
    }
    $headers = @{ 'User-Agent' = 'SteamCardsBot-Updater'; 'Accept' = 'application/vnd.github+json' }
    # Use the commits list endpoint with the branch as a query parameter.
    # This avoids GitHub/API gateways interpreting slashes in branch names as URL path separators.
    $encodedBranch = [Uri]::EscapeDataString($Branch)
    $commitUrl = "https://api.github.com/repos/$Repo/commits?sha=$encodedBranch&per_page=1"
    try {
        $remoteCommits = Invoke-RestMethod -Uri $commitUrl -Headers $headers -TimeoutSec 25
        $remote = @($remoteCommits) | Select-Object -First 1
        if (-not $remote) { throw "GitHub returned no commits for branch '$Branch'." }
    } catch {
        throw ("Не удалось прочитать commit GitHub (URL: $commitUrl). Проверь доступность репозитория/ветки и подключение. Исходная ошибка: " + $_.Exception.Message)
    }
    $remoteSha = [string]$remote.sha
    if ([string]::IsNullOrWhiteSpace($remoteSha) -or $remoteSha -notmatch '^[0-9a-f]{40}$') {
        throw 'GitHub returned an invalid commit SHA.'
    }
    $localSha = ''
    if (Test-Path -LiteralPath $Marker) { $localSha = (Get-Content -LiteralPath $Marker -Raw -ErrorAction SilentlyContinue).Trim() }
    if (-not $Force -and $localSha -eq $remoteSha) {
        Log "Already current ($remoteSha)."
        exit 0
    }
    $tempRoot = Join-Path $env:TEMP ('cardbot_update_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    try {
        $zip = Join-Path $tempRoot 'source.zip'
        $extract = Join-Path $tempRoot 'source'
        $zipUrl = "https://codeload.github.com/$Repo/zip/refs/heads/$Branch"
        try {
            Invoke-WebRequest -Uri $zipUrl -OutFile $zip -Headers @{ 'User-Agent' = 'SteamCardsBot-Updater' } -TimeoutSec 90
        } catch {
            throw ("Не удалось скачать архив ветки с GitHub (URL: $zipUrl). Проверь доступность репозитория/ветки. Исходная ошибка: " + $_.Exception.Message)
        }
        Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
        $source = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
        if (-not $source) { throw 'Downloaded archive has no source directory.' }
        $files = @(
            'bot.py','funpay_orders.py','order_parser.py','playerok_monitor.py','playerok_orders.py',
            'runtime_paths.py','sales_analytics.py','run_bot.ps1','start.bat','update_bot.ps1',
            'requirements.txt','requirements-playerok.txt','configure_playerok.bat','configure_playerok.ps1',
            'install_autostart.ps1','setup_windows.ps1','toggle_autostart_task.ps1','repair_updater.bat'
        )
        $available = @($files | Where-Object { Test-Path -LiteralPath (Join-Path $source.FullName $_) })
        if (-not ($available -contains 'bot.py') -or -not ($available -contains 'start.bat') -or -not ($available -contains 'run_bot.ps1')) {
            throw 'Archive is missing one or more required launcher files; update aborted.'
        }
        # Syntax check the candidate Python file before touching the installed version.
        $py = Get-Command py -ErrorAction SilentlyContinue
        if ($py) {
            & py -3 -m py_compile (Join-Path $source.FullName 'bot.py')
            if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed; installed files were not changed.' }
        } else { Log 'WARNING: py.exe not found; Python syntax check skipped.' }
        New-Item -ItemType Directory -Path $Backup -Force | Out-Null
        foreach ($relative in $available) {
            $target = Join-Path $Root $relative
            if (Test-Path -LiteralPath $target) {
                $backupTarget = Join-Path $Backup $relative
                $parent = Split-Path -Parent $backupTarget
                if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
                Copy-Item -LiteralPath $target -Destination $backupTarget -Force
            }
        }
        try {
            foreach ($relative in $available) {
                Copy-Item -LiteralPath (Join-Path $source.FullName $relative) -Destination (Join-Path $Root $relative) -Force
            }
            [IO.File]::WriteAllText($Marker, $remoteSha + [Environment]::NewLine, [Text.Encoding]::ASCII)
        } catch {
            Log "Copy failed; rolling back files from $Backup"
            foreach ($relative in $available) {
                $backupTarget = Join-Path $Backup $relative
                if (Test-Path -LiteralPath $backupTarget) {
                    Copy-Item -LiteralPath $backupTarget -Destination (Join-Path $Root $relative) -Force
                }
            }
            throw
        }
        Log "Update installed successfully: $remoteSha"
        Log "Backup created at: $Backup"
    } finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
    }
} catch {
    Log ("UPDATE FAILED: " + $_.Exception.Message)
    Write-Host 'Update failed. The existing bot files were left in place or restored from backup.' -ForegroundColor Red
    exit 1
}
