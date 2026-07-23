$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$updater = Join-Path $PSScriptRoot "update.ps1"
$taskName = "SpaceWorks Automatic Production Update"

if (-not (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)) {
  throw "Windows Task Scheduler cmdlets are unavailable. Schedule scripts/update.ps1 hourly."
}

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$updater`"" `
  -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger `
  -Once `
  -At (Get-Date).AddMinutes(5) `
  -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask `
  -TaskName $taskName `
  -Description "Checks GitHub Releases hourly and safely updates Space Works production." `
  -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Automatic Space Works updates are scheduled hourly."
