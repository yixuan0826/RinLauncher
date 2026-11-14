param(
  [string]$Target = $PSScriptRoot,
  [string]$Manifest = "",
  [switch]$Check,
  [switch]$Restore,
  [switch]$Force
)

# Rin Launcher standalone repair helper.
# Keep this file ASCII-only: Windows PowerShell 5.1 parses it without BOM.
#
#   repair.ps1 -Check
#       Verify install-manifest.json (missing / hash mismatch).
#   repair.ps1 -Restore
#       Copy the newest backup-* directory over the install, keeping data/.
#   repair.ps1 -Restore -Force
#       Same, but does not ask for confirmation.

$ErrorActionPreference = 'Stop'
$Target = (Resolve-Path -LiteralPath $Target).Path
if (-not $Manifest) { $Manifest = Join-Path $Target 'install-manifest.json' }

function Write-Line([string]$Text) {
  Write-Host $Text
}

# Use the .NET crypto API instead of Get-FileHash: this script may be launched
# from a PowerShell 7 environment whose PSModulePath hides Windows PowerShell
# 5.1's Microsoft.PowerShell.Utility module.
function Get-Sha256([string]$Path) {
  $stream = [System.IO.File]::OpenRead($Path)
  try {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
      $bytes = $sha.ComputeHash($stream)
      return ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLower()
    } finally {
      $sha.Dispose()
    }
  } finally {
    $stream.Dispose()
  }
}

function Test-Install {
  if (-not (Test-Path -LiteralPath $Manifest)) {
    Write-Line "manifest not found: $Manifest"
    return 2
  }
  $data = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
  $problems = 0
  foreach ($entry in $data.files.PSObject.Properties) {
    $file = Join-Path $Target $entry.Name
    if (-not (Test-Path -LiteralPath $file)) {
      Write-Line "missing: $($entry.Name)"
      $problems++
      continue
    }
    $hash = Get-Sha256 $file
    if ($hash -ne $entry.Value.ToLower()) {
      Write-Line "hash mismatch: $($entry.Name)"
      $problems++
    }
  }
  $count = @($data.files.PSObject.Properties).Count
  Write-Line "checked $count file(s), $problems problem(s)"
  if ($problems -gt 0) { return 1 }
  return 0
}

function Get-LatestBackup {
  $backups = Get-ChildItem -LiteralPath $Target -Directory -Force |
    Where-Object { $_.Name -like 'backup-*' } |
    Sort-Object LastWriteTime -Descending
  if (-not $backups) { return $null }
  return $backups[0].FullName
}

function Restore-Backup {
  $backup = Get-LatestBackup
  if (-not $backup) {
    Write-Line "no backup-* directory found under $Target"
    return 2
  }
  Write-Line "restoring from $backup"
  if (-not $Force) {
    $answer = Read-Host "This overwrites program files (data/ is kept). Continue? [y/N]"
    if ($answer -notin @('y', 'Y', 'yes', 'YES')) {
      Write-Line "cancelled"
      return 3
    }
  }
  Get-ChildItem -LiteralPath $backup -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $Target -Recurse -Force -ErrorAction Stop
  }
  Remove-Item -LiteralPath (Join-Path $Target 'updates\update-in-progress.json') `
    -Force -ErrorAction SilentlyContinue
  Write-Line "restored; start RinLauncher.exe again"
  return 0
}

if ($Restore) {
  exit (Restore-Backup)
}
exit (Test-Install)
