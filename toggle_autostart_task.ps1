# CardBot auto-start helper v2 — supports state-preserving migration
$ErrorActionPreference = 'Stop'
$taskName = 'CardBot - AutoStart'
$startFile = 'C:\CardBot\start.bat'
$logFile = 'C:\CardBot\autostart_task.log'
$mutexName = 'Global\CardBotAutoStartTaskToggle'
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$locked = $false

function Write-TaskLog([string]$Message) {
    try {
        Add-Content -LiteralPath $logFile -Encoding UTF8 -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    } catch { }
}

function Test-LegacyAutostartValue {
    $runPath = 'Software\Microsoft\Windows\CurrentVersion\Run'
    $runKey = $null
    try {
        $runKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($runPath, $false)
        if ($null -eq $runKey) { return $false }
        $value = $runKey.GetValue('CardBotFarmAutostart', $null)
        return -not [string]::IsNullOrWhiteSpace([string]$value)
    } finally {
        if ($null -ne $runKey) { $runKey.Dispose() }
    }
}

function Remove-LegacyAutostartValue {
    $runPath = 'Software\Microsoft\Windows\CurrentVersion\Run'
    $runKey = $null
    try {
        $runKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($runPath, $true)
        if ($null -ne $runKey) {
            $runKey.DeleteValue('CardBotFarmAutostart', $false)
        }
    } finally {
        if ($null -ne $runKey) { $runKey.Dispose() }
    }
}

function Register-AutostartTask {
    if (-not (Test-Path -LiteralPath $startFile -PathType Leaf)) {
        throw 'Не найден C:\CardBot\start.bat; задача не изменена.'
    }
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR 'System32\cmd.exe') -Argument ('/d /c ""' + $startFile + '""') -WorkingDirectory 'C:\CardBot'
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Starts Steam Card Bot on user logon.' -Force | Out-Null
}

try {
    try { $locked = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Переключение автозапуска уже выполняется.' }

    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    $legacyEnabled = Test-LegacyAutostartValue
    $mode = [Environment]::GetEnvironmentVariable('CARDBOT_AUTOSTART_MODE', 'Process')

    if ($mode -eq 'MIGRATE') {
        # Preserve the old setting during first launch: old Run ON becomes scheduled task ON.
        if ($null -eq $existing -and $legacyEnabled) {
            Register-AutostartTask
            $operation = 'MIGRATED'
        } else {
            $operation = 'UNCHANGED'
        }
    } elseif ($null -eq $existing -and $legacyEnabled) {
        # When migration failed, a manual toggle from old ON should turn auto-start OFF.
        $operation = 'DISABLED'
    } elseif ($null -eq $existing -or $existing.State -eq 'Disabled') {
        Register-AutostartTask
        $operation = 'ENABLED'
    } else {
        Disable-ScheduledTask -TaskName $taskName -ErrorAction Stop | Out-Null
        $operation = 'DISABLED'
    }

    # Only clean the legacy value after the replacement is registered or the explicit toggle succeeds.
    $legacyClean = $true
    try {
        Remove-LegacyAutostartValue
    } catch {
        $legacyClean = $false
        Write-TaskLog ("WARNING: task action $operation completed but legacy Run value could not be removed: " + $_.Exception.Message)
    }

    if ($operation -ne 'UNCHANGED') { Write-TaskLog "Auto-start task changed to $operation." }
    if ($legacyClean) { Write-Output $operation }
    else { Write-Output ($operation + '_LEGACY_ENTRY_REMAINS') }
} catch {
    Write-TaskLog ("ERROR: " + $_.Exception.Message)
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
