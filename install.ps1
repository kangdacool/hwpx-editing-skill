<#
Install the hwpx-editing skill into an AI agent's skills directory (Windows).

Usage:
  ./install.ps1 <agent> [<agent> ...]   copy the skill into each agent's dir
  ./install.ps1 all                     install into every known agent
  ./install.ps1 -Link claude            symlink instead of copy (needs admin/Dev Mode)

Agents: claude  codex  cursor  gemini  openclaw
#>
param(
  [switch]$Link,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Agents
)

$ErrorActionPreference = "Stop"
$SkillName = "hwpx-editing"
$RepoDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src       = Join-Path $RepoDir "skills\$SkillName"

if (-not $Agents -or $Agents.Count -eq 0) {
  Write-Host "Nothing to do. Example:  ./install.ps1 claude"; exit 1
}
if ($Agents -contains "all") {
  $Agents = @("claude", "codex", "cursor", "gemini", "openclaw")
}
if (-not (Test-Path (Join-Path $Src "SKILL.md"))) {
  Write-Error "SKILL.md not found under $Src — run this from the repo root."; exit 1
}

function Dest-Base($agent) {
  switch ($agent) {
    "claude"   { Join-Path $HOME ".claude\skills" }
    "codex"    { Join-Path $HOME ".codex\skills" }
    "cursor"   { Join-Path (Get-Location) ".cursor\skills" }   # project-scoped
    "gemini"   { Join-Path $HOME ".gemini\skills" }
    "openclaw" { Join-Path $HOME ".openclaw\skills" }
    default    { throw "Unknown agent: $agent" }
  }
}

foreach ($agent in $Agents) {
  $base = Dest-Base $agent
  $dest = Join-Path $base $SkillName
  New-Item -ItemType Directory -Force -Path $base | Out-Null
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  if ($Link) {
    New-Item -ItemType SymbolicLink -Path $dest -Target $Src | Out-Null
    Write-Host "linked  $agent  ->  $dest  ->  $Src"
  } else {
    Copy-Item -Recurse -Force $Src $dest
    Write-Host "copied  $agent  ->  $dest"
  }
}

Write-Host ""
Write-Host "Done. Restart your agent (or start a new session)."
Write-Host "Claude Code: type /skills and look for '$SkillName'."
Write-Host "Python dep:  pip install lxml"
Write-Host "Sanity check: python `"$Src\scripts\selftest.py`""
