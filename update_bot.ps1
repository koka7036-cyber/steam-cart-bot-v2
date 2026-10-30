param(
    [switch]$Force,
    [switch]$CheckOnly,
    [switch]$WaitForBot,
    [switch]$Restart,
    [string]$ExpectedSha
)

$ErrorActionPreference = 'Stop'
$Repo = 'koka7036-cyber/steam-cart-bot-v2'
$Branch = 'main'
$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$Log = Join-Path $Root 'update_bot.log'
$Marker = Join-Path $Root '.bot_update_commit.txt'
$CredentialTarget = 'SteamCardsBot-GitHubReadOnly'
$Backup = Join-Path $Root ('backups\update_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Write-UpdateLog([string]$Message) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-BotProcesses {
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and $_.CommandLine -match 'bot\.py'
    })
}

if (-not ('CardBot.CredentialManager' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
namespace CardBot {
    public static class CredentialManager {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct CREDENTIAL {
            public UInt32 Flags;
            public UInt32 Type;
            public string TargetName;
            public string Comment;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
            public UInt32 CredentialBlobSize;
            public IntPtr CredentialBlob;
            public UInt32 Persist;
            public UInt32 AttributeCount;
            public IntPtr Attributes;
            public string TargetAlias;
            public string UserName;
        }

        [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credentialPtr);

        [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CredWrite(ref CREDENTIAL credential, UInt32 flags);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern void CredFree(IntPtr buffer);

        public static string Read(string target) {
            IntPtr ptr;
            if (!CredRead(target, 1, 0, out ptr)) return null;
            try {
                CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(ptr, typeof(CREDENTIAL));
                if (c.CredentialBlob == IntPtr.Zero || c.CredentialBlobSize == 0) return null;
                return Marshal.PtrToStringUni(c.CredentialBlob, (int)c.CredentialBlobSize / 2);
            } finally {
                CredFree(ptr);
            }
        }

        public static void Write(string target, string username, string secret) {
            byte[] blob = Encoding.Unicode.GetBytes(secret);
            GCHandle handle = GCHandle.Alloc(blob, GCHandleType.Pinned);
            try {
                CREDENTIAL c = new CREDENTIAL();
                c.Type = 1;
                c.TargetName = target;
                c.UserName = username;
                c.Persist = 2;
                c.CredentialBlobSize = (UInt32)blob.Length;
                c.CredentialBlob = handle.AddrOfPinnedObject();
                if (!CredWrite(ref c, 0)) {
                    throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                }
            } finally {
                handle.Free();
                Array.Clear(blob, 0, blob.Length);
            }
        }
    }
}
'@
}

try {
    Write-UpdateLog ('Checking GitHub repository {0}, branch {1}' -f $Repo, $Branch)

    $githubToken = ''
    $saveCredential = $false
    if (-not [string]::IsNullOrWhiteSpace($env:GH_TOKEN)) {
        $githubToken = $env:GH_TOKEN
    } elseif (-not [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
        $githubToken = $env:GITHUB_TOKEN
    } else {
        try {
            $githubToken = [CardBot.CredentialManager]::Read($CredentialTarget)
        } catch {
            Write-UpdateLog ('Credential Manager read failed: ' + $_.Exception.Message)
        }
    }

    if ([string]::IsNullOrWhiteSpace($githubToken)) {
        if ($env:CARD_BOT_NONINTERACTIVE -eq '1' -or $CheckOnly -and $env:CARD_BOT_NONINTERACTIVE -eq '1') {
            throw 'GitHub token is not saved. Run update_bot.ps1 manually once to register it securely.'
        }
        Write-Host ''
        Write-Host 'Enter a fine-grained read-only GitHub token once. Input is hidden.'
        $secureToken = Read-Host 'GitHub token' -AsSecureString
        if (-not $secureToken -or $secureToken.Length -eq 0) {
            throw 'No GitHub token supplied. No files were changed.'
        }
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
        try {
            $githubToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
        $saveCredential = $true
    }

    $headers = @{
        'User-Agent' = 'SteamCardsBot-Updater'
        'Accept' = 'application/vnd.github+json'
        'Authorization' = 'Bearer ' + $githubToken
    }
    $encodedBranch = [Uri]::EscapeDataString($Branch)
    $commitUrl = 'https://api.github.com/repos/{0}/commits?sha={1}&per_page=1' -f $Repo, $encodedBranch
    try {
        $remoteCommits = Invoke-RestMethod -Uri $commitUrl -Headers $headers -TimeoutSec 25
    } catch {
        if ($saveCredential) {
            throw ('GitHub rejected the token or is unavailable. The new token was NOT saved. ' + $_.Exception.Message)
        }
        throw ('Could not read the latest GitHub commit. ' + $_.Exception.Message)
    }

    $remote = @($remoteCommits) | Select-Object -First 1
    if (-not $remote) {
        throw ('GitHub returned no commits for branch ' + $Branch + '.')
    }
    $remoteSha = [string]$remote.sha
    if ([string]::IsNullOrWhiteSpace($remoteSha) -or $remoteSha -notmatch '^[0-9a-f]{40}$') {
        throw 'GitHub returned an invalid commit SHA.'
    }
    if ($ExpectedSha -and $remoteSha -ne $ExpectedSha) {
        throw 'The main branch changed after the update check. Check for updates again before installing.'
    }

    # Save a newly entered token only after the API accepted it and returned a valid SHA.
    if ($saveCredential) {
        [CardBot.CredentialManager]::Write($CredentialTarget, 'github-readonly', $githubToken)
        Write-UpdateLog 'GitHub token saved in Windows Credential Manager.'
    }

    $localSha = ''
    if (Test-Path -LiteralPath $Marker -PathType Leaf) {
        $localSha = (Get-Content -LiteralPath $Marker -Raw -ErrorAction Stop).Trim()
    }

    if (-not $Force -and $localSha -eq $remoteSha) {
        Write-UpdateLog ('Already current: ' + $remoteSha)
        Write-Output ('CURRENT:' + $remoteSha)
        exit 0
    }

    if ($CheckOnly) {
        Write-UpdateLog ('Update available: ' + $remoteSha)
        Write-Output ('UPDATE_AVAILABLE:' + $remoteSha)
        exit 0
    }

    if ($WaitForBot) {
        $deadline = (Get-Date).AddSeconds(120)
        while ((Get-BotProcesses).Count -gt 0 -and (Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 1
        }
    }

    $runningBots = Get-BotProcesses
    if ($runningBots.Count -gt 0) {
        throw 'Bot is still running. Stop it before updating; installed files were not changed.'
    }

    $tempRoot = Join-Path $env:TEMP ('cardbot_update_' + [guid]::NewGuid().ToString('N'))
    $extractRoot = Join-Path $tempRoot 'source'
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

    try {
        $zipPath = Join-Path $tempRoot 'source.zip'
        $zipUrl = 'https://codeload.github.com/{0}/zip/{1}' -f $Repo, $remoteSha
        Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -Headers @{
            'User-Agent' = 'SteamCardsBot-Updater'
            'Authorization' = 'Bearer ' + $githubToken
        } -TimeoutSec 90

        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
        $source = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
        if (-not $source) {
            throw 'Downloaded GitHub archive has no source directory.'
        }

        $files = @(
            'bot.py', 'funpay_orders.py', 'order_parser.py', 'playerok_monitor.py',
            'playerok_orders.py', 'runtime_paths.py', 'sales_analytics.py', 'steam_inventory.py',
            'run_bot.ps1', 'start.bat', 'update_bot.ps1',
            'requirements.txt', 'requirements-playerok.txt',
            'configure_playerok.bat', 'configure_playerok.ps1',
            'install_autostart.ps1', 'setup_windows.ps1',
            'toggle_autostart_task.ps1', 'repair_updater.bat'
        )

        $available = @($files | Where-Object {
            Test-Path -LiteralPath (Join-Path $source.FullName $_) -PathType Leaf
        })
        foreach ($required in @('bot.py', 'steam_inventory.py', 'start.bat', 'run_bot.ps1', 'update_bot.ps1')) {
            if ($available -notcontains $required) {
                throw ('Archive is missing required file: ' + $required)
            }
        }

        $py = Get-Command py -ErrorAction SilentlyContinue
        if (-not $py) {
            throw 'Python Launcher py.exe was not found. Installed files were not changed.'
        }
        & py -3 -m compileall -q $source.FullName
        if ($LASTEXITCODE -ne 0) {
            throw 'Python compile check failed. Installed files were not changed.'
        }

        $psFiles = @($available | Where-Object { $_ -like '*.ps1' })
        foreach ($relative in $psFiles) {
            $candidate = Join-Path $source.FullName $relative
            $tokens = $null
            $parseErrors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($candidate, [ref]$tokens, [ref]$parseErrors) | Out-Null
            if ($parseErrors.Count -gt 0) {
                throw ('PowerShell parser check failed for ' + $relative + ': ' + $parseErrors[0].Message)
            }
        }

        New-Item -ItemType Directory -Path $Backup -Force | Out-Null
        $preExisting = @{}
        foreach ($relative in $available) {
            $target = Join-Path $Root $relative
            $preExisting[$relative] = Test-Path -LiteralPath $target -PathType Leaf
            if ($preExisting[$relative]) {
                $backupTarget = Join-Path $Backup $relative
                $backupParent = Split-Path -Parent $backupTarget
                New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
                Copy-Item -LiteralPath $target -Destination $backupTarget -Force
            }
        }

        try {
            foreach ($relative in $available) {
                Copy-Item -LiteralPath (Join-Path $source.FullName $relative) -Destination (Join-Path $Root $relative) -Force
            }
            [IO.File]::WriteAllText($Marker, $remoteSha + [Environment]::NewLine, [Text.Encoding]::ASCII)
        } catch {
            Write-UpdateLog ('Copy failed; rolling back from ' + $Backup)
            foreach ($relative in $available) {
                $target = Join-Path $Root $relative
                $backupTarget = Join-Path $Backup $relative
                if ($preExisting[$relative] -and (Test-Path -LiteralPath $backupTarget -PathType Leaf)) {
                    Copy-Item -LiteralPath $backupTarget -Destination $target -Force
                } elseif (-not $preExisting[$relative] -and (Test-Path -LiteralPath $target -PathType Leaf)) {
                    Remove-Item -LiteralPath $target -Force
                }
            }
            throw
        }

        Write-UpdateLog ('Update installed: ' + $remoteSha)
        Write-UpdateLog ('Backup saved: ' + $Backup)
        Write-Output ('UPDATED:' + $remoteSha)

        if ($Restart) {
            $startFile = Join-Path $Root 'start.bat'
            $previousNonInteractive = $env:CARD_BOT_NONINTERACTIVE
            $env:CARD_BOT_NONINTERACTIVE = '1'
            try {
                $arguments = '/d /c call "' + $startFile + '"'
                Start-Process -FilePath $env:ComSpec -ArgumentList $arguments -WorkingDirectory $Root | Out-Null
            } finally {
                $env:CARD_BOT_NONINTERACTIVE = $previousNonInteractive
            }
            Write-UpdateLog 'Restart launcher started.'
        }
    } finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
} catch {
    Write-UpdateLog ('UPDATE FAILED: ' + $_.Exception.Message)
    Write-Output ('ERROR:' + $_.Exception.Message)
    if ($Restart) {
        $startFile = Join-Path $Root 'start.bat'
        if (Test-Path -LiteralPath $startFile -PathType Leaf) {
            $deadline = (Get-Date).AddSeconds(45)
            while (((Get-BotProcesses).Count -gt 0 -or @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -match 'run_bot\.ps1' }).Count -gt 0) -and (Get-Date) -lt $deadline) {
                Start-Sleep -Seconds 1
            }
            if ((Get-BotProcesses).Count -eq 0) {
                $previousNonInteractive = $env:CARD_BOT_NONINTERACTIVE
                $env:CARD_BOT_NONINTERACTIVE = '1'
                try {
                    Start-Process -FilePath $env:ComSpec -ArgumentList ('/d /c call "' + $startFile + '"') -WorkingDirectory $Root | Out-Null
                } finally {
                    $env:CARD_BOT_NONINTERACTIVE = $previousNonInteractive
                }
                Write-UpdateLog 'Old installed version restart requested after update failure.'
            }
        }
    }
    exit 1
}
