param(
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$Repo = 'koka7036-cyber/steam-cart-bot-v2'
$Branch = 'main'
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
    # Read token from Windows Credential Manager. Prompt only if no valid saved token exists.
    $credentialTarget = 'SteamCardsBot-GitHubReadOnly'
    $githubToken = ''
    $saveCredential = $false
    if ($env:GH_TOKEN) { $githubToken = $env:GH_TOKEN }
    elseif ($env:GITHUB_TOKEN) { $githubToken = $env:GITHUB_TOKEN }

    if ([string]::IsNullOrWhiteSpace($githubToken)) {
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
    [DllImport("advapi32.dll", EntryPoint="CredReadW", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credentialPtr);
    [DllImport("advapi32.dll", EntryPoint="CredWriteW", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern bool CredWrite(ref CREDENTIAL credential, UInt32 flags);
    [DllImport("advapi32.dll", SetLastError=true)]
    private static extern void CredFree(IntPtr buffer);
    public static string Read(string target) {
        IntPtr ptr;
        if (!CredRead(target, 1, 0, out ptr)) return null;
        try {
            CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(ptr, typeof(CREDENTIAL));
            if (c.CredentialBlob == IntPtr.Zero || c.CredentialBlobSize == 0) return null;
            return Marshal.PtrToStringUni(c.CredentialBlob, (int)c.CredentialBlobSize / 2);
        } finally { CredFree(ptr); }
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
            if (!CredWrite(ref c, 0)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        } finally { handle.Free(); Array.Clear(blob, 0, blob.Length); }
    }
}
}
'@
        }
        try { $githubToken = [CardBot.CredentialManager]::Read($credentialTarget) }
        catch {
            Log ('WARNING: Windows Credential Manager read failed: ' + $_.Exception.Message)
            $githubToken = ''
        }
    }

    if ([string]::IsNullOrWhiteSpace($githubToken)) {
        if ($env:CARD_BOT_NONINTERACTIVE -eq '1') {
            throw 'No GitHub credential is saved. Start the bot manually once and save a read-only token before enabling unattended updates.'
        }
        Write-Host ''
        Write-Host 'GitHub token required once. Input is hidden; token will be saved in Windows Credential Manager.'
        $secureToken = Read-Host 'GitHub token (hidden)' -AsSecureString
        if (-not $secureToken -or $secureToken.Length -eq 0) {
            throw 'No GitHub token supplied. No files were changed.'
        }
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
        try { $githubToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        $saveCredential = $true
    }

    $headers['Authorization'] = 'Bearer ' + $githubToken
    $encodedBranch = [Uri]::EscapeDataString($Branch)
    $commitUrl = "https://api.github.com/repos/$Repo/commits?sha=$encodedBranch&per_page=1"
    try {
        $remoteCommits = Invoke-RestMethod -Uri $commitUrl -Headers $headers -TimeoutSec 25
        $remote = @($remoteCommits) | Select-Object -First 1
        if (-not $remote) { throw "GitHub returned no commits for branch '$Branch'." }
    } catch {
        if ($saveCredential) {
            throw ('GitHub rejected the token or could not be reached. The new token was NOT saved. ' + $_.Exception.Message)
        }
        throw ("Could not read GitHub commit. Check repository access and connection. " + $_.Exception.Message)
    }
    $remoteSha = [string]$remote.sha
    if ([string]::IsNullOrWhiteSpace($remoteSha) -or $remoteSha -notmatch '^[0-9a-f]{40}    $localSha = ''
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
        # Pin the archive to the exact commit whose SHA was checked above. The branch can move between API lookup and download.
        $zipUrl = "https://codeload.github.com/$Repo/zip/$remoteSha"
        try {
            Invoke-WebRequest -Uri $zipUrl -OutFile $zip -Headers @{ 'User-Agent' = 'SteamCardsBot-Updater'; 'Authorization' = ('Bearer ' + $githubToken) } -TimeoutSec 90
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
) {
        throw 'GitHub returned an invalid commit SHA.'
    }
    if ($saveCredential) {
        try {
            [CardBot.CredentialManager]::Write($credentialTarget, 'github-readonly', $githubToken)
            Log 'GitHub token saved in Windows Credential Manager.'
        } catch {
            throw ('GitHub access worked, but saving the token in Windows Credential Manager failed. ' + $_.Exception.Message)
        }
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
        # Pin the archive to the exact commit whose SHA was checked above. The branch can move between API lookup and download.
        $zipUrl = "https://codeload.github.com/$Repo/zip/$remoteSha"
        try {
            Invoke-WebRequest -Uri $zipUrl -OutFile $zip -Headers @{ 'User-Agent' = 'SteamCardsBot-Updater'; 'Authorization' = ('Bearer ' + $githubToken) } -TimeoutSec 90
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
