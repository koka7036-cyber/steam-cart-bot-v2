$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot '..\update_bot.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Error $_.Message }
    exit 1
}
$scriptText = Get-Content -LiteralPath $source -Raw
if (-not $scriptText) { throw 'Updater file is empty.' }
if ($scriptText -notmatch 'SteamCardsBot-GitHubReadOnly') { throw 'Credential Manager target is missing.' }
if ($scriptText -notmatch 'CredReadW' -or $scriptText -notmatch 'CredWriteW') { throw 'Credential Manager native read/write APIs are missing.' }
$apiIndex = $scriptText.IndexOf('$remoteCommits = Invoke-RestMethod')
$shaIndex = $scriptText.IndexOf('GitHub returned an invalid commit SHA.')
$saveIndex = $scriptText.IndexOf("[CardBot.CredentialManager]::Write($credentialTarget, 'github-readonly', $githubToken)")
if ($apiIndex -lt 0 -or $shaIndex -lt $apiIndex -or $saveIndex -lt $shaIndex) {
    throw 'A newly entered token must be saved only after a valid GitHub SHA is returned.'
}
if ($scriptText -match '\.github_token\.dpapi') { throw 'Legacy DPAPI token file should not be used by this updater.' }
if ($scriptText -notmatch 'c\.Persist\s*=\s*2') { throw 'Credential must persist across logons.' }
if ($scriptText -notmatch 'c\.Type\s*=\s*1') { throw 'Credential must be stored as a generic credential.' }
if ($scriptText -notmatch '\$Branch\s*=\s*''main''') { throw 'Updater must target main.' }
if ($scriptText -notmatch '\$headers\[''Authorization''\]\s*=\s*''Bearer ''\s*\+\s*\$githubToken') { throw 'GitHub Bearer token authorization header is missing.' }
$tryCount = ([regex]::Matches($scriptText, '(?m)^\s*try\s*\{')).Count
$catchCount = ([regex]::Matches($scriptText, '(?m)^\s*catch\s*\{')).Count
if ($tryCount -lt 3 -or $catchCount -lt 2) { throw 'Credential load/save error handling blocks are missing.' }
Write-Host 'Updater syntax and credential storage contract verified.'
