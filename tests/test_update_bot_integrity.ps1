$ErrorActionPreference = 'Stop'

$source = Join-Path $PSScriptRoot '..\update_bot.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Error $_.Message }
    exit 1
}

$functionNames = @('Get-CardBotGitBlobSha', 'Test-CardBotTreeIntegrity')
$definitions = $ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $functionNames -contains $node.Name
}, $true)
$foundNames = @($definitions | ForEach-Object { $_.Name })
foreach ($name in $functionNames) {
    if ($foundNames -notcontains $name) {
        throw "Updater function is missing: $name"
    }
}
$functionSource = ($definitions | ForEach-Object { $_.Extent.Text }) -join [Environment]::NewLine
. ([ScriptBlock]::Create($functionSource))

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('cardbot-integrity-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    $filePath = Join-Path $tempRoot 'bot.py'
    [IO.File]::WriteAllText($filePath, ("print('first')" + [Environment]::NewLine), (New-Object System.Text.UTF8Encoding($false)))
    $expectedHash = Get-CardBotGitBlobSha -Path $filePath
    if ($expectedHash -notmatch '^[0-9a-f]{40}$') {
        throw 'Git blob SHA must be a 40-character lowercase SHA-1.'
    }

    $tree = @{ 'bot.py' = $expectedHash }
    $valid = Test-CardBotTreeIntegrity -Root $tempRoot -Paths @('bot.py') -RequiredPaths @('bot.py') -RemoteTree $tree
    if (-not $valid.IsValid) {
        throw ('Identical local file was rejected: ' + $valid.Reason)
    }

    [IO.File]::WriteAllText($filePath, ("print('changed')" + [Environment]::NewLine), (New-Object System.Text.UTF8Encoding($false)))
    $changed = Test-CardBotTreeIntegrity -Root $tempRoot -Paths @('bot.py') -RequiredPaths @('bot.py') -RemoteTree $tree
    if ($changed.IsValid) {
        throw 'Modified local file was incorrectly accepted as the expected GitHub commit.'
    }

    Remove-Item -LiteralPath $filePath -Force
    $missing = Test-CardBotTreeIntegrity -Root $tempRoot -Paths @('bot.py') -RequiredPaths @('bot.py') -RemoteTree $tree
    if ($missing.IsValid) {
        throw 'Missing required local file was incorrectly accepted.'
    }

    $missingRemote = Test-CardBotTreeIntegrity -Root $tempRoot -Paths @('bot.py') -RequiredPaths @('bot.py') -RemoteTree @{}
    if ($missingRemote.IsValid) {
        throw 'Missing required remote Git tree entry was incorrectly accepted.'
    }

    Write-Host 'Updater local Git tree integrity tests passed.'
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
