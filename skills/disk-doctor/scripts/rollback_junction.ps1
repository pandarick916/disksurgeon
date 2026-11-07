# rollback_junction.ps1
# Undo a junction move: remove the junction (link only) and move the data back.
# FAIL-CLOSED: without -Force it refuses.
# Usage:
#   ... -File rollback_junction.ps1 -Source "C:\Users\me\.codex" -Target "D:\AgentData\.codex" -Force
#   Source = the junction path (what the app sees), Target = where the real data now lives.

param(
  [Parameter(Mandatory=$true)][string]$Source,
  [Parameter(Mandatory=$true)][string]$Target,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$logDir = Join-Path $env:TEMP 'junction_moves'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$log = Join-Path $logDir ("rollback_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".log")

function Log($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -LiteralPath $log -Value $line -Encoding UTF8
}

Log "Source (junction) = $Source"
Log "Target (data)     = $Target"

$si = Get-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
if (-not $si) { Log "ABORT: source not found."; exit 2 }
if ($si.LinkType -ne 'Junction') { Log "ABORT: source is not a junction."; exit 2 }
if (-not (Test-Path -LiteralPath $Target -PathType Container)) { Log "ABORT: target data not found."; exit 2 }
if (-not $Force) { Log "REFUSED: pass -Force to execute (fail-closed)."; exit 3 }

# remove the junction only; [Directory]::Delete(false) does NOT recurse into the target
try {
  [System.IO.Directory]::Delete($Source, $false)
} catch {
  Log ("REMOVE JUNCTION FAILED: {0}" -f $_.Exception.Message)
  exit 4
}
Log "Junction removed."

# move data back
$argList = @("$Target", "$Source", "/MOVE", "/E", "/COPY:DAT", "/R:1", "/W:1", "/NFL", "/NDL", "/NP")
& robocopy.exe @argList
$rc = $LASTEXITCODE
Log ("robocopy exit = {0}" -f $rc)
if ($rc -ge 8) { Log "WARN: rollback move had errors; check manually."; exit 5 }

Log "DONE rollback. Log: $log"
