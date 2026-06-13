# Triggers the live Hyatt fetch on GitHub Actions.
# First run: prompts for a GitHub Personal Access Token, saves it, and
# creates a "Run Hyatt" shortcut on your Desktop that calls this same
# script directly. Subsequent runs just fire the workflow.

$ErrorActionPreference = "Stop"
$repo = "Lionnevergrowup/Hyatt-checker"
$workflow = "weekly-live.yml"
$tokenFile = "$env:USERPROFILE\.hyatt-pat"
$shortcutPath = "$env:USERPROFILE\Desktop\Run Hyatt.lnk"

function Setup-Token {
    Write-Host ""
    Write-Host "=== One-time setup: create a GitHub Personal Access Token ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Open this URL in any browser (phone is fine):"
    Write-Host "   https://github.com/settings/tokens/new?description=Hyatt-checker%20trigger&scopes=workflow"
    Write-Host ""
    Write-Host "2. Pick an expiration (1 year is fine; longer = less hassle)."
    Write-Host ""
    Write-Host "3. Make sure the 'workflow' scope is checked."
    Write-Host ""
    Write-Host "4. Click 'Generate token' at the bottom. Copy the token (starts with ghp_)."
    Write-Host ""
    $token = Read-Host -Prompt "Paste token here"
    $token = $token.Trim()
    if (-not $token) {
        Write-Host "No token entered. Aborting." -ForegroundColor Red
        exit 1
    }
    Set-Content -Path $tokenFile -Value $token -NoNewline -Encoding UTF8
    Write-Host "Saved." -ForegroundColor Green
}

function Setup-Shortcut {
    Write-Host ""
    Write-Host "Creating Desktop shortcut..." -ForegroundColor Cyan
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $shortcut.WorkingDirectory = Split-Path $PSCommandPath
    $shortcut.IconLocation = "powershell.exe,0"
    $shortcut.Description = "Trigger a Hyatt points refresh"
    $shortcut.Save()
    Write-Host "Created: $shortcutPath" -ForegroundColor Green
    Write-Host "(Double-click it next time you want fresh data.)" -ForegroundColor Gray
}

# First-run: setup if needed
if (-not (Test-Path $tokenFile)) { Setup-Token }
if (-not (Test-Path $shortcutPath)) { Setup-Shortcut }

# Read token
$token = (Get-Content $tokenFile -Raw).Trim()
if (-not $token) {
    Write-Host "Token file is empty. Delete $tokenFile and re-run." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# Fire the workflow
$url = "https://api.github.com/repos/$repo/actions/workflows/$workflow/dispatches"
$body = '{"ref": "main"}'
$headers = @{
    "Authorization" = "Bearer $token"
    "Accept" = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent" = "hyatt-checker-trigger"
}

Write-Host ""
Write-Host "Triggering workflow..." -ForegroundColor Cyan
try {
    Invoke-RestMethod -Method POST -Uri $url -Headers $headers -Body $body | Out-Null
    Write-Host ""
    Write-Host "Workflow started. Track progress at:" -ForegroundColor Green
    Write-Host "   https://github.com/$repo/actions"
    Write-Host ""
    Write-Host "When the run goes green (~20-30 min), refresh the page:"
    Write-Host "   https://lionnevergrowup.github.io/Hyatt-checker/"
    Write-Host ""
    Start-Sleep -Seconds 6
}
catch {
    Write-Host ""
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    $status = $null
    try { $status = $_.Exception.Response.StatusCode.value__ } catch {}
    if ($status -eq 401 -or $status -eq 403) {
        Write-Host ""
        Write-Host "Token rejected. It may have expired or have the wrong scope."
        Write-Host "Delete $tokenFile and double-click 'Run Hyatt' again to set a new one."
    }
    Read-Host "Press Enter to close"
}
