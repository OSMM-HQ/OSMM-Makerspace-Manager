$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$updater = Join-Path $PSScriptRoot "update.ps1"
$taskName = "SpaceWorks Automatic Production Update"
$compose = @("compose", "-f", "docker-compose.prod.yml")

if (-not (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)) {
  throw "Windows Task Scheduler cmdlets are unavailable. Schedule scripts/update.ps1 every five minutes."
}

docker @compose exec -T backend python manage.py update_control set-auto on *> $null
if ($LASTEXITCODE -ne 0) { throw "The running Space Works backend could not enable automatic updates." }

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$updater`"" `
  -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger `
  -Once `
  -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask `
  -TaskName $taskName `
  -Description "Checks GitHub Releases every five minutes and safely updates Space Works production." `
  -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "Automatic Space Works updates are enabled and checked every five minutes."
