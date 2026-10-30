$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot '..\update_bot.ps1'
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Error $_.Message }
    exit 1
}
if (-not ($scriptText = Get-Content -LiteralPath $source -Raw)) { throw 'Updater file is empty.' }
if ($scriptText -notmatch 'SteamCardsBot-GitHubReadOnly') { throw 'Credential Manager target is missing.' }
if ($scriptText -notmatch 'CredReadW' -or $scriptText -notmatch 'CredWriteW') { throw 'Credential Manager native read/write APIs are missing.' }
if ($scriptText -match '\.github_token\.dpapi') { throw 'Legacy DPAPI token file should not be used by this updater.' }
Write-Host 'Updater syntax and credential storage contract verified.'
