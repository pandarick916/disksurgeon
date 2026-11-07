# scan_big_dirs.ps1
# Read-only scan: C: free space + common AI folder sizes / junction status.
# This script does NOT move or delete anything.

param(
  [string[]]$Paths
)

$ErrorActionPreference = 'SilentlyContinue'

# ---- C: drive space ----
$drv = $env:SystemDrive.TrimEnd(':')
$c = Get-PSDrive $drv
"$($env:SystemDrive) used {0:N1} GB / total {1:N1} GB / free {2:N1} GB" -f ($c.Used/1GB), (($c.Used+$c.Free)/1GB), ($c.Free/1GB)
""

# ---- candidate folders ----
$defaults = @(
  "$env:USERPROFILE\.codex",
  "$env:USERPROFILE\.workbuddy",
  "$env:USERPROFILE\.claude",
  "$env:USERPROFILE\.cursor",
  "$env:USERPROFILE\.gemini",
  "$env:USERPROFILE\.ollama",
  "$env:USERPROFILE\.cache",
  "$env:USERPROFILE\.npm",
  "$env:USERPROFILE\.config",
  "$env:APPDATA\Codex",
  "$env:APPDATA\WorkBuddyX",
  "$env:APPDATA\CodeBuddy CN",
  "$env:LOCALAPPDATA\Docker"
)
if (-not $Paths -or $Paths.Count -eq 0) { $candidates = $defaults } else { $candidates = $Paths }

"{0,-14} {1,-10} {2}" -f "Size", "Type", "Path"
"{0,-14} {1,-10} {2}" -f "--------------", "----------", "----"

foreach ($p in $candidates) {
  if (-not (Test-Path $p)) { continue }
  $i = Get-Item $p -Force
  if ($i.LinkType -eq 'Junction') {
    $size = "-> " + ($i.Target -join ';')
    $type = "Junction"
  } else {
    $sum = (Get-ChildItem $p -Recurse -File -Force | Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) { $sum = 0 }
    $size = "{0:N0} MB" -f ($sum/1MB)
    $type = "Folder"
  }
  "{0,-14} {1,-10} {2}" -f $size, $type, $p
}

""
"Tip: use WizTree for a full-disk treemap."
"Note: size scan may be slow. Read-only; nothing is moved or deleted."
