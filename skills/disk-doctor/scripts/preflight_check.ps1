# preflight_check.ps1
# Read-only pre-flight check before moving a folder + creating a junction.
# Does NOT move or delete anything. Prints GO / NO-GO.
# Usage:
#   powershell -ExecutionPolicy Bypass -File preflight_check.ps1 -Source "C:\Users\me\.codex" -Target "D:\AgentData\.codex"

param(
  [Parameter(Mandatory=$true)][string]$Source,
  [Parameter(Mandatory=$true)][string]$Target
)

$ErrorActionPreference = 'SilentlyContinue'
$script:ok = $true

function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red;    $script:ok = $false }
function Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Pass($m) { Write-Host "[ OK ] $m" -ForegroundColor Green }

Write-Host "Source : $Source"
Write-Host "Target : $Target"
Write-Host ""

# 1) source exists and is a real folder
if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
  Fail "Source is missing or not a folder."
} else {
  $si = Get-Item -LiteralPath $Source -Force
  if ($si.LinkType) { Fail "Source is already a link ($($si.LinkType)). Nothing to do." }
  else { Pass "Source is a real folder." }
}

# 2) target drive exists
$tQual = Split-Path -Qualifier $Target
$tDriveName = $tQual.TrimEnd(':')
$tDrive = Get-PSDrive $tDriveName -ErrorAction SilentlyContinue
if (-not $tDrive) { Fail "Target drive does not exist: $tQual" }
else { Pass "Target drive $tQual exists." }

# 3) target must not already contain data
if (Test-Path -LiteralPath $Target) {
  $cnt = (Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue | Measure-Object).Count
  if ($cnt -gt 0) { Fail "Target already exists and is not empty." }
  else { Warn "Target exists but is empty; it will be reused." }
}

# 4) source and target on different drives (otherwise pointless)
if ($si -and $si.PSDrive -and ($si.PSDrive.Name -eq $tDriveName)) {
  Warn "Source and target are on the same drive; this will not free space."
}

# 5) target free space >= source size * 1.1
$srcSize = 0
$srcCount = 0
if (Test-Path -LiteralPath $Source -PathType Container) {
  $files = Get-ChildItem -LiteralPath $Source -Recurse -File -Force -ErrorAction SilentlyContinue
  $srcSize = ($files | Measure-Object -Property Length -Sum).Sum
  $srcCount = ($files | Measure-Object).Count
  if ($null -eq $srcSize) { $srcSize = 0 }
}
if ($tDrive -and $tDrive.Free) {
  $need = $srcSize * 1.1
  if ($tDrive.Free -lt $need) {
    Fail ("Target free {0:N1} GB < needed {1:N1} GB" -f ($tDrive.Free/1GB), ($need/1GB))
  } else {
    Pass ("Target free {0:N1} GB, needed {1:N1} GB" -f ($tDrive.Free/1GB), ($srcSize/1GB))
  }
}

Write-Host ""
Write-Host ("Source size : {0:N1} MB ({1} files)" -f ($srcSize/1MB), $srcCount)
if ($script:ok) { Write-Host "RESULT: GO" -ForegroundColor Green; exit 0 }
else           { Write-Host "RESULT: NO-GO" -ForegroundColor Red;  exit 1 }
