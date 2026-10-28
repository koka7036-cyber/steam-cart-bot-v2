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

try {
    try { $locked = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Переключение автозапуска уже выполняется.' }

    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -eq $existing -or $existing.State -eq 'Disabled') {
        if (-not (Test-Path -LiteralPath $startFile -PathType Leaf)) {
            throw 'Не найден C:\CardBot\start.bat; задача не изменена.'
        }
        $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $action = New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR 'System32\cmd.exe') -Argument ('/d /c ""' + $startFile + '""') -WorkingDirectory 'C:\CardBot'
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Starts Steam Card Bot on user logon.' -Force | Out-Null
        Write-TaskLog 'Auto-start task enabled.'
        Write-Output 'ENABLED'
    } else {
        Disable-ScheduledTask -TaskName $taskName -ErrorAction Stop | Out-Null
        Write-TaskLog 'Auto-start task disabled.'
        Write-Output 'DISABLED'
    }
} catch {
    Write-TaskLog ("ERROR: " + $_.Exception.Message)
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
