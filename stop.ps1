[CmdletBinding()]
param(
    [switch]$StopDatabase
)

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "            DocuMind AI - Safe Shutdown Script              " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

function Stop-ProcessOnPort {
    param(
        [int]$Port,
        [string]$ServiceName
    )

    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        $pids = if ($conns) { $conns | Select-Object -ExpandProperty OwningProcess -Unique } else { @() }
        if (-not $pids) {
            $lines = netstat -ano -p tcp | Select-String ":$Port\s+.*LISTENING\s+(\d+)"
            if ($lines) {
                $pids = $lines | ForEach-Object {
                    if ($_ -match 'LISTENING\s+(\d+)') { [int]$matches[1] }
                } | Select-Object -Unique
            }
        }

        if ($pids) {
            foreach ($processId in $pids) {
                $p = Get-Process -Id $processId -ErrorAction SilentlyContinue
                if ($p) {
                    Write-Host "  Stopping $ServiceName (PID: $processId, $($p.ProcessName))..." -ForegroundColor Yellow
                    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                }
            }
            Write-Host "  $ServiceName stopped." -ForegroundColor Green
        }
        else {
            Write-Host "  $ServiceName (Port $Port) is not running." -ForegroundColor Gray
        }
    }
    catch {
        Write-Host "  Could not inspect/stop port $Port : $_" -ForegroundColor DarkYellow
    }
}

# Stop Frontend (Port 5173)
Stop-ProcessOnPort -Port 5173 -ServiceName "Frontend (Vite)"

# Stop Backend (Port 8000)
Stop-ProcessOnPort -Port 8000 -ServiceName "Backend (FastAPI)"

# Close any remaining PowerShell dev windows titled "DocuMind *"
$devWindows = Get-Process -Name powershell -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like "DocuMind Backend*" -or $_.MainWindowTitle -like "DocuMind Frontend*"
}
if ($devWindows) {
    foreach ($win in $devWindows) {
        Write-Host "  Closing console window '$($win.MainWindowTitle)'..." -ForegroundColor Yellow
        Stop-Process -Id $win.Id -Force -ErrorAction SilentlyContinue
    }
}

if ($StopDatabase) {
    Write-Host ""
    Write-Host "  Stopping PostgreSQL container..." -ForegroundColor Yellow
    & docker compose --project-directory $projectRoot stop postgres
    Write-Host "  PostgreSQL container stopped. Database volumes and data preserved." -ForegroundColor Green
}
else {
    Write-Host ""
    Write-Host "  Note: PostgreSQL container remains running in Docker." -ForegroundColor Gray
    Write-Host "  To also stop PostgreSQL, run: .\stop.bat -StopDatabase" -ForegroundColor Gray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " DocuMind AI application services stopped cleanly." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
