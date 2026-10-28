$ErrorActionPreference = 'Stop'

# Installs a per-user logon task. It does not start the bot immediately.
$botRoot = 'C:\CardBot'
$startFile = Join-Path $botRoot 'start.bat'
$taskName = 'Steam Card Bot - AutoStart'

if (-not (Test-Path -LiteralPath $startFile -PathType Leaf)) {
    throw "Не найден $startFile. Сначала установи рабочую версию бота в C:\CardBot."
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR 'System32\cmd.exe') -Argument ('/c ""' + $startFile + '""') -WorkingDirectory $botRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Starts the Steam card Telegram bot after this user signs in.' -Force | Out-Null

Write-Host "Автозапуск настроен: $taskName"
Write-Host 'Задача запускает C:\CardBot\start.bat при входе в Windows и не запускает второй экземпляр.'
Write-Host 'Чтобы проверить сейчас, запусти C:\CardBot\start.bat вручную или нажми Run у задачи в Планировщике заданий.'
