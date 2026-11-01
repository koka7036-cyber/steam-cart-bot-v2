# Read-only Windows acceptance preflight for Steam Cart Bot v2.
# This script does not start the bot, call external APIs, modify files,
# change settings, enable/disable Scheduled Tasks, or print secret values.

$ErrorActionPreference = 'Stop'
$script:Failures = 0
$script:Warnings = 0
$script:Checks = 0

function Write-Check {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][ValidateSet('PASS', 'WARN', 'BLOCK')][string]$Status,
        [Parameter(Mandatory = $true)][string]$Details
    )
    $script:Checks++
    if ($Status -eq 'BLOCK') { $script:Failures++ }
    if ($Status -eq 'WARN') { $script:Warnings++ }
    $prefix = switch ($Status) {
        'PASS' { '[PASS]' }
        'WARN' { '[WARN]' }
        'BLOCK' { '[BLOCK]' }
    }
    Write-Output ("{0} {1}: {2}" -f $prefix, $Name, $Details)
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($env:CARDBOT_DATA_DIR -and -not [string]::IsNullOrWhiteSpace($env:CARDBOT_DATA_DIR)) {
    $DataDir = [System.IO.Path]::GetFullPath($env:CARDBOT_DATA_DIR)
} else {
    $DataDir = $Root
}

Write-Output 'Steam Cart Bot v2 — read-only acceptance preflight'
Write-Output ("Repository: {0}" -f $Root)
Write-Output ("Data directory: {0}" -f $DataDir)
Write-Output 'No bot process or marketplace operation will be started.'
Write-Output ''

# Platform and project files.
if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    Write-Check 'Windows platform' 'PASS' 'Windows detected.'
} else {
    Write-Check 'Windows platform' 'BLOCK' 'This acceptance script must run on the target Windows PC.'
}

$RequiredFiles = @(
    'bot.py',
    'runtime_paths.py',
    'admin_navigation.py',
    'steam_inventory.py',
    'funpay_orders.py',
    'playerok_orders.py',
    'playerok_monitor.py',
    'order_parser.py',
    'sales_analytics.py',
    'requirements.txt',
    'requirements-playerok.txt',
    'start.bat',
    'run_bot.ps1',
    'update_bot.ps1'
)
foreach ($RelativePath in $RequiredFiles) {
    $FullPath = Join-Path $Root $RelativePath
    if (Test-Path -LiteralPath $FullPath -PathType Leaf) {
        Write-Check ("File " + $RelativePath) 'PASS' 'Present.'
    } else {
        Write-Check ("File " + $RelativePath) 'BLOCK' 'Required project file is missing.'
    }
}

# Environment variables: report presence only, never values.
foreach ($VariableName in @('TG_TOKEN', 'STEAM_ID', 'STEAM_LOGIN')) {
    $Value = [Environment]::GetEnvironmentVariable($VariableName, 'Process')
    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        Write-Check ("Environment " + $VariableName) 'PASS' 'Set; value hidden.'
    } else {
        Write-Check ("Environment " + $VariableName) 'BLOCK' 'Missing in this PowerShell process; value was not requested or displayed.'
    }
}

$PlayerokToken = [Environment]::GetEnvironmentVariable('PLAYEROK_TOKEN', 'Process')
if ([string]::IsNullOrWhiteSpace($PlayerokToken)) {
    Write-Check 'Playerok configuration' 'WARN' 'PLAYEROK_TOKEN is not set in this process; Playerok monitor will remain unconfigured.'
} else {
    $PlayerokVariables = @('PLAYEROK_USER_AGENT', 'PLAYEROK_ITEM_1_SET_ID', 'PLAYEROK_ITEM_5_SET_ID')
    $MissingPlayerok = @()
    foreach ($VariableName in $PlayerokVariables) {
        $Value = [Environment]::GetEnvironmentVariable($VariableName, 'Process')
        if ([string]::IsNullOrWhiteSpace($Value)) { $MissingPlayerok += $VariableName }
    }
    if ($MissingPlayerok.Count -gt 0) {
        Write-Check 'Playerok configuration' 'BLOCK' ("PLAYEROK_TOKEN exists but required companion variables are missing: " + ($MissingPlayerok -join ', ') + '. Values were not displayed.')
    } else {
        $OneId = [Environment]::GetEnvironmentVariable('PLAYEROK_ITEM_1_SET_ID', 'Process')
        $FiveId = [Environment]::GetEnvironmentVariable('PLAYEROK_ITEM_5_SET_ID', 'Process')
        if ($OneId -eq $FiveId) {
            Write-Check 'Playerok listing mapping' 'BLOCK' 'One-set and five-set listing IDs are identical; values were not displayed.'
        } else {
            Write-Check 'Playerok configuration' 'PASS' 'Token, user-agent and distinct listing mappings are present; values hidden.'
        }
    }
}

# Python launcher and dependency imports; do not import bot.py.
$PythonCommand = Get-Command py -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    Write-Check 'Python launcher' 'BLOCK' 'The Windows py launcher was not found.'
} else {
    $PythonVersionOutput = & py -3 -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Check 'Python launcher' 'BLOCK' 'py -3 could not start Python.'
    } else {
        $PythonVersion = [string]$PythonVersionOutput
        $VersionParts = $PythonVersion.Split('.')
        $VersionOk = ($VersionParts.Count -ge 2 -and [int]$VersionParts[0] -ge 3 -and [int]$VersionParts[1] -ge 10)
        if ($VersionOk) {
            Write-Check 'Python version' 'PASS' ("Python " + $PythonVersion + '.')
        } else {
            Write-Check 'Python version' 'BLOCK' ("Python " + $PythonVersion + ' detected; Python 3.10 or newer is required.')
        }

        $DependencyOutput = & py -3 -c "import requests, rsa, telebot; print('OK')" 2>&1
        if ($LASTEXITCODE -eq 0 -and [string]$DependencyOutput -match 'OK') {
            Write-Check 'Core Python dependencies' 'PASS' 'requests, rsa and pyTelegramBotAPI imports succeeded.'
        } else {
            Write-Check 'Core Python dependencies' 'BLOCK' 'One or more required imports failed; inspect the local Python environment.'
        }

        if (-not [string]::IsNullOrWhiteSpace($PlayerokToken)) {
            $SdkOutput = & py -3 -c "from importlib.metadata import version; print(version('PyPlayerokAPI'))" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Check 'Playerok SDK' 'PASS' ("Optional SDK installed (" + [string]$SdkOutput + '). No account was accessed.')
            } else {
                Write-Check 'Playerok SDK' 'BLOCK' 'PLAYEROK_TOKEN is configured but PyPlayerokAPI is not installed in this Python environment.'
            }
        } else {
            Write-Check 'Playerok SDK' 'WARN' 'Skipped because Playerok is not configured in this process.'
        }

        $PythonParseCode = @'
import ast
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
files = [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]
errors = []
for path in files:
    try:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except Exception as exc:
        errors.append((str(path.relative_to(root)), type(exc).__name__))
if errors:
    for name, kind in errors:
        print(f"{name}: {kind}")
    sys.exit(1)
print(f"Parsed {len(files)} Python files without writing bytecode.")
'@
        $ParseOutput = & py -3 -c $PythonParseCode $Root 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Check 'Python syntax' 'PASS' ([string]$ParseOutput)
        } else {
            Write-Check 'Python syntax' 'BLOCK' ([string]($ParseOutput -join ' '))
        }
    }
}

# Parse all project PowerShell scripts without executing them.
$PowerShellFiles = @(Get-ChildItem -LiteralPath $Root -Filter '*.ps1' -File -Recurse -ErrorAction SilentlyContinue)
$PowerShellErrors = @()
foreach ($File in $PowerShellFiles) {
    $Tokens = $null
    $ParseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $File.FullName,
        [ref]$Tokens,
        [ref]$ParseErrors
    ) | Out-Null
    if ($ParseErrors.Count -gt 0) {
        $PowerShellErrors += ($File.Name + ': ' + $ParseErrors[0].Message)
    }
}
if ($PowerShellErrors.Count -eq 0) {
    Write-Check 'PowerShell syntax' 'PASS' ("Parsed {0} PowerShell files; none were executed." -f $PowerShellFiles.Count)
} else {
    Write-Check 'PowerShell syntax' 'BLOCK' ($PowerShellErrors -join '; ')
}

# Inspect local JSON structure without displaying contents.
function Test-JsonFile {
    param([string]$Name, [string]$RequiredProperty)
    $Path = Join-Path $DataDir $Name
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Write-Check ("Data " + $Name) 'WARN' 'File not present; it may be created on first authorized run.'
        return
    }
    try {
        $Object = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -eq $Object -or $null -eq $Object.PSObject.Properties[$RequiredProperty]) {
            Write-Check ("Data " + $Name) 'BLOCK' ("JSON is valid but required property '" + $RequiredProperty + "' is missing.")
        } else {
            Write-Check ("Data " + $Name) 'PASS' 'JSON parsed and required top-level property is present; contents hidden.'
        }
    } catch {
        Write-Check ("Data " + $Name) 'BLOCK' 'JSON is unreadable or malformed; file was not changed.'
    }
}

Test-JsonFile -Name 'vouchers.json' -RequiredProperty 'vouchers'
Test-JsonFile -Name 'funpay_orders.json' -RequiredProperty 'orders'
Test-JsonFile -Name 'playerok_orders.json' -RequiredProperty 'orders'

$FunPayConfigPath = Join-Path $DataDir 'funpay_config.json'
if (Test-Path -LiteralPath $FunPayConfigPath -PathType Leaf) {
    try {
        $FunPayConfig = Get-Content -LiteralPath $FunPayConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($FunPayConfig.auto_delivery_funpay -eq $true) {
            Write-Check 'FunPay auto-delivery setting' 'BLOCK' 'Auto-delivery is currently enabled in the local config; this script did not change it.'
        } else {
            Write-Check 'FunPay auto-delivery setting' 'PASS' 'Auto-delivery is not enabled in the local config.'
        }
    } catch {
        Write-Check 'FunPay config' 'BLOCK' 'Configuration JSON is malformed; file was not changed.'
    }
} else {
    Write-Check 'FunPay config' 'WARN' 'funpay_config.json is not present in the data directory.'
}

# Check the inventory cache age only; do not read or display inventory IDs.
$InventoryPath = Join-Path $DataDir 'inventory_cache.json'
if (Test-Path -LiteralPath $InventoryPath -PathType Leaf) {
    $AgeHours = ((Get-Date) - (Get-Item -LiteralPath $InventoryPath).LastWriteTime).TotalHours
    if ($AgeHours -gt 6 -or $AgeHours -lt -0.1) {
        Write-Check 'Inventory cache freshness' 'BLOCK' ("Cache age is {0:N1} hours; refresh the cache manually before any delivery test." -f $AgeHours)
    } else {
        Write-Check 'Inventory cache freshness' 'PASS' ("Cache file age is {0:N1} hours; no inventory content was read." -f $AgeHours)
    }
} else {
    Write-Check 'Inventory cache freshness' 'WARN' 'Inventory cache file is not present; no cache was generated.'
}

# Verify scheduled-task state without changing the task.
try {
    $Task = Get-ScheduledTask -TaskName 'CardBot - AutoStart' -ErrorAction Stop
    if ($Task.Settings.Enabled -eq $true) {
        Write-Check 'Windows auto-start task' 'BLOCK' 'CardBot - AutoStart is enabled. It was not modified.'
    } else {
        Write-Check 'Windows auto-start task' 'PASS' 'CardBot - AutoStart exists but is disabled.'
    }
} catch {
    Write-Check 'Windows auto-start task' 'WARN' 'CardBot - AutoStart was not found or could not be read. No task was created.'
}

# Report repository revision/working tree without modifying it.
$GitCommand = Get-Command git -ErrorAction SilentlyContinue
if ($GitCommand) {
    $Revision = & git -C $Root rev-parse --short HEAD 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Check 'Git revision' 'PASS' ([string]$Revision)
        $Dirty = & git -C $Root status --porcelain 2>$null
        if ($LASTEXITCODE -eq 0 -and $Dirty) {
            Write-Check 'Git working tree' 'WARN' 'Uncommitted local changes exist; they were not modified.'
        } elseif ($LASTEXITCODE -eq 0) {
            Write-Check 'Git working tree' 'PASS' 'Clean.'
        }
    } else {
        Write-Check 'Git revision' 'WARN' 'The project directory is not a Git working tree.'
    }
} else {
    Write-Check 'Git revision' 'WARN' 'Git executable was not found.'
}

Write-Output ''
Write-Output ("Checks: {0}; Blocks: {1}; Warnings: {2}" -f $script:Checks, $script:Failures, $script:Warnings)
Write-Output 'This preflight is read-only. It did not start the bot, connect to Steam/FunPay/Playerok/Telegram, change settings, modify files, or enable auto-start.'
if ($script:Failures -gt 0) {
    Write-Output 'RESULT: BLOCKED — resolve the reported issues before any acceptance delivery test.'
    exit 2
}
Write-Output 'RESULT: PREFLIGHT PASSED — this is not authorization for real sales. Continue with the separate manual acceptance checklist.'
exit 0
