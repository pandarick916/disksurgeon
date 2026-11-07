# move_with_junction.ps1
# Move a folder to another drive, then create a directory junction at the original path.
# FAIL-CLOSED: without -Force it only does a dry run. Nothing is moved unless -Force is passed.
# Usage:
#   dry run : ... -File move_with_junction.ps1 -Source "C:\Users\me\.codex" -Target "D:\AgentData\.codex" -DryRun
#   execute : ... -File move_with_junction.ps1 -Source "C:\Users\me\.codex" -Target "D:\AgentData\.codex" -Force

param(
  [Parameter(Mandatory=$true)][string]$Source,
  [Parameter(Mandatory=$true)][string]$Target,
  [switch]$Force,
  [switch]$DryRun,
  [switch]$AllowRisky
)

$ErrorActionPreference = 'Stop'
$logDir = Join-Path $env:TEMP 'junction_moves'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$log = Join-Path $logDir ("move_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".log")

function Log($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

Log "Source = $Source"
Log "Target = $Target"

# ---- preflight ----
$si = Get-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
if (-not $si) { Log "ABORT: source not found."; exit 2 }
if ($si.LinkType) { Log "ABORT: source is already a link ($($si.LinkType))."; exit 2 }

# ---- safety gate: refuse critical / system / OneDrive paths ----
$fullSrc = $si.FullName.TrimEnd('\')
$risky = $false
$riskyHit = ""
$riskyRoots = @(
  (Join-Path $env:SystemDrive 'Windows'),
  (Join-Path $env:SystemDrive 'Program Files'),
  (Join-Path $env:SystemDrive 'Program Files (x86)'),
  (Join-Path $env:SystemDrive 'ProgramData'),
  (Join-Path $env:SystemDrive 'Users\Public'),
  (Join-Path $env:USERPROFILE 'Desktop'),
  (Join-Path $env:USERPROFILE 'Documents'),
  (Join-Path $env:USERPROFILE 'Downloads'),
  (Join-Path $env:USERPROFILE 'Pictures'),
  (Join-Path $env:USERPROFILE 'Music'),
  (Join-Path $env:USERPROFILE 'Videos')
)
foreach ($r in $riskyRoots) {
  if ($fullSrc -ieq $r -or $fullSrc -like ($r + '\*')) { $risky = $true; $riskyHit = $r; break }
}
if ($fullSrc -match '^[A-Za-z]:$') { $risky = $true; $riskyHit = 'drive root' }
if ($fullSrc -match 'OneDrive') { $risky = $true; $riskyHit = 'OneDrive path' }
if ($risky -and -not $AllowRisky) {
  Log ("ABORT: refusing risky path ($riskyHit). Pass -AllowRisky only if you are absolutely sure.")
  exit 7
}
if ($Source.Length -gt 240) { Log "WARN: source path longer than 240 chars; junction may hit MAX_PATH." }

$tQual = Split-Path -Qualifier $Target
$tDriveName = $tQual.TrimEnd(':')
$tDrive = Get-PSDrive $tDriveName -ErrorAction SilentlyContinue
if (-not $tDrive) { Log "ABORT: target drive $tQual not found."; exit 2 }

# The junction LINK is created at the source path, so the SOURCE volume must be NTFS.
# The TARGET volume can be exFAT/FAT (verified on this machine), but ACLs/permissions are not preserved.
$sVol = Get-Volume -DriveLetter $si.PSDrive.Name -ErrorAction SilentlyContinue
if ($sVol -and $sVol.FileSystem -ne 'NTFS') {
  Log ("ABORT: source volume is {0}; the junction link requires NTFS." -f $sVol.FileSystem)
  exit 2
}
$tVol = Get-Volume -DriveLetter $tDriveName -ErrorAction SilentlyContinue
if ($tVol -and $tVol.FileSystem -ne 'NTFS') {
  Log ("NOTE: target is {0} (not NTFS); ACLs/permissions will NOT be preserved." -f $tVol.FileSystem)
}

if (Test-Path -LiteralPath $Target) {
  $cnt = (Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue | Measure-Object).Count
  if ($cnt -gt 0) { Log "ABORT: target exists and is not empty."; exit 2 }
}

$files = Get-ChildItem -LiteralPath $Source -Recurse -File -Force -ErrorAction SilentlyContinue
$srcSize = ($files | Measure-Object -Property Length -Sum).Sum
$srcCount = ($files | Measure-Object).Count
if ($null -eq $srcSize) { $srcSize = 0 }
Log ("Source: {0:N1} MB, {1} files" -f ($srcSize/1MB), $srcCount)

if ($tDrive.Free -lt ($srcSize * 1.1)) { Log "ABORT: not enough free space on target."; exit 2 }

if ($DryRun) { Log "DRY RUN: plan OK. Nothing changed."; exit 0 }
if (-not $Force) { Log "REFUSED: pass -Force to execute (fail-closed)."; exit 3 }

# ---- move (robocopy is robust for large trees / long paths) ----
Log "Moving with robocopy /MOVE ..."
$argList = @("$Source", "$Target", "/MOVE", "/E", "/COPY:DAT", "/R:1", "/W:1", "/NFL", "/NDL", "/NP")
& robocopy.exe @argList
$rc = $LASTEXITCODE
Log ("robocopy exit = {0}" -f $rc)
if ($rc -ge 8) {
  Log "ABORT: move reported errors. Source left as-is; no junction created."
  exit 4
}

# ---- make sure the original path is empty before creating the junction ----
if (Test-Path -LiteralPath $Source) {
  $left = (Get-ChildItem -LiteralPath $Source -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object).Count
  if ($left -gt 0) { Log ("ABORT: source still has {0} items. Not deleting." -f $left); exit 5 }
  Remove-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
}
if (Test-Path -LiteralPath $Source) { Log "ABORT: cannot clear source path."; exit 5 }

# ---- create junction (native, avoids cmd.exe) ----
try {
  New-Item -ItemType Junction -Path $Source -Target $Target -ErrorAction Stop | Out-Null
} catch {
  Log ("JUNCTION FAILED: {0}" -f $_.Exception.Message)
  exit 6
}
$chk = Get-Item -LiteralPath $Source -Force
if ($chk.LinkType -ne 'Junction') { Log "ABORT: junction not detected."; exit 6 }

# ---- verify ----
$dstFiles = Get-ChildItem -LiteralPath $Target -Recurse -File -Force -ErrorAction SilentlyContinue
$dstCount = ($dstFiles | Measure-Object).Count
$dstSize = ($dstFiles | Measure-Object -Property Length -Sum).Sum
Log ("Verify: target {0:N1} MB, {1} files (expected {2})" -f ($dstSize/1MB), $dstCount, $srcCount)
if ($dstCount -ne $srcCount) { Log "WARN: file count mismatch; check manually." }
Log "DONE. Junction created. Log: $log"
