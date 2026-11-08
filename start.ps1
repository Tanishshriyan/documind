[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipMigrations,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$venvRoot = Join-Path $backendRoot ".venv"
$pythonExe = Join-Path $venvRoot "Scripts\python.exe"
$alembicExe = Join-Path $venvRoot "Scripts\alembic.exe"
$alembicIni = Join-Path $backendRoot "alembic.ini"

function Assert-CommandAvailable {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' is required but was not found on PATH."
    }
}

function Test-DockerReady {
    try {
        & docker info 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Ensure-DockerReady {
    if (-not (Test-DockerReady)) {
        $dockerDesktopCandidates = @(
            (Join-Path ${env:ProgramFiles} "Docker\Docker\Docker Desktop.exe"),
            (Join-Path ${env:LOCALAPPDATA} "Programs\Docker\Docker\Docker Desktop.exe")
        )
        $dockerDesktop = $dockerDesktopCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $dockerDesktop) {
            throw "Docker Desktop is not installed. Install Docker Desktop for Windows, enable Linux containers, then run .\start.ps1 again."
        }

        Write-Host "Docker is installed but not running. Opening Docker Desktop..." -ForegroundColor Yellow
        Start-Process -FilePath $dockerDesktop | Out-Null
        for ($attempt = 1; $attempt -le 60; $attempt++) {
            if (Test-DockerReady) {
                break
            }
            if ($attempt -eq 60) {
                throw "Docker Desktop did not become ready after 120 seconds. Open Docker Desktop, wait until it says 'Running', then run .\start.ps1 again."
            }
            Start-Sleep -Seconds 2
        }
    }

    $dockerOsType = (& docker info --format "{{.OSType}}" 2>$null).Trim()
    if ($dockerOsType -ne "linux") {
        throw "Docker is running with '$dockerOsType' containers. Switch Docker Desktop to Linux containers, then run .\start.ps1 again."
    }
}

function Get-ProcessByPort {
    param([int]$Port)

    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conns) {
            $owningPids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
            return Get-Process -Id $owningPids -ErrorAction SilentlyContinue
        }
    }
    catch {}

    $lines = netstat -ano -p tcp | Select-String ":$Port\s+.*LISTENING\s+(\d+)"
    if ($lines) {
        $foundPids = $lines | ForEach-Object {
            if ($_ -match 'LISTENING\s+(\d+)') { [int]$matches[1] }
        } | Select-Object -Unique
        return Get-Process -Id $foundPids -ErrorAction SilentlyContinue
    }
    return @()
}

function Test-EndpointQuick {
    param(
        [string]$Url,
        [int[]]$ExpectedStatusCodes = @(200)
    )

    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return ($ExpectedStatusCodes -contains $resp.StatusCode)
    }
    catch {
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
            return ($ExpectedStatusCodes -contains $code)
        }
        return $false
    }
}

function Wait-ForEndpoint {
    param(
        [string]$Url,
        [string]$ServiceName,
        [int]$TimeoutSeconds = 30,
        [int[]]$ExpectedStatusCodes = @(200)
    )

    Write-Host "  Waiting for $ServiceName to be ready ($Url)..." -NoNewline
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-EndpointQuick -Url $Url -ExpectedStatusCodes $ExpectedStatusCodes) {
            Write-Host " Ready." -ForegroundColor Green
            return $true
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
    Write-Host " Timeout!" -ForegroundColor Red
    return $false
}

function Start-DevWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command
    )

    $windowCommand = "& { `$Host.UI.RawUI.WindowTitle = '$Title'; $Command }"
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $windowCommand) `
        -WorkingDirectory $WorkingDirectory
}

function Open-Browser {
    param([string]$Url)

    Write-Host "  Launching default browser: $Url" -ForegroundColor Cyan
    try {
        Start-Process $Url | Out-Null
    }
    catch {
        Start-Process "cmd.exe" -ArgumentList @("/c", "start", $Url) | Out-Null
    }
}

# -------------------------------------------------------------
# Main Startup Pipeline
# -------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "         DocuMind AI - One-Click Application Startup        " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Stage 1: Prerequisites
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow
Assert-CommandAvailable "docker"
Assert-CommandAvailable "python"
Assert-CommandAvailable "npm"
Ensure-DockerReady
Write-Host "  Prerequisites verified (Docker, Python, npm)." -ForegroundColor Green

# Environment configuration
$backendEnv = Join-Path $backendRoot ".env"
if (-not (Test-Path -LiteralPath $backendEnv)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination $backendEnv
    Write-Host "  Created backend/.env from .env.example." -ForegroundColor Yellow
}
if (Test-Path -LiteralPath $backendEnv) {
    $envLines = Get-Content -LiteralPath $backendEnv
    $jwtMatch = $envLines | Where-Object { $_ -match '^JWT_SECRET_KEY=\s*$' }
    if ($jwtMatch) {
        $generatedKey = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
        $updatedLines = $envLines | ForEach-Object {
            if ($_ -match '^JWT_SECRET_KEY=\s*$') { "JWT_SECRET_KEY=$generatedKey" } else { $_ }
        }
        Set-Content -LiteralPath $backendEnv -Value $updatedLines
        Write-Host "  Generated secure local JWT_SECRET_KEY in backend/.env" -ForegroundColor Green
    }
}

# Root .env mirror for docker compose
$rootEnv = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $rootEnv) -and (Test-Path -LiteralPath $backendEnv)) {
    Copy-Item -LiteralPath $backendEnv -Destination $rootEnv
}

# Stage 2: Database
Write-Host "[2/6] Starting PostgreSQL database..." -ForegroundColor Yellow
& docker compose --project-directory $projectRoot up -d postgres
if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL could not be started. Make sure Docker Desktop is running."
}

Write-Host "  Waiting for PostgreSQL container health check..." -NoNewline
$postgresReady = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    $health = (& docker compose --project-directory $projectRoot ps postgres --format "{{.Health}}" 2>$null).Trim()
    if ($health -eq "healthy") {
        $postgresReady = $true
        Write-Host " Healthy." -ForegroundColor Green
        break
    }
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 1
}
if (-not $postgresReady) {
    Write-Host ""
    throw "PostgreSQL did not become healthy. Check 'docker compose logs postgres'."
}

# Virtual Environment & Dependencies
if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Host "  Creating backend virtual environment..." -ForegroundColor Yellow
    & python -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not create the backend virtual environment." }
}

if (-not $SkipInstall) {
    Write-Host "  Verifying dependencies..." -ForegroundColor Yellow
    & $pythonExe -m pip install -q -r (Join-Path $backendRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
        Write-Host "  Installing frontend npm dependencies..." -ForegroundColor Yellow
        Push-Location $frontendRoot
        try { & npm.cmd install }
        finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    }
}

# Stage 3: Database Migrations
Write-Host "[3/6] Applying database migrations..." -ForegroundColor Yellow
if (-not $SkipMigrations) {
    Push-Location $backendRoot
    try { & $alembicExe -c $alembicIni upgrade head }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "Database migrations failed. Check the alembic output above." }
    Write-Host "  Database migrations are up to date." -ForegroundColor Green
} else {
    Write-Host "  Migrations skipped (-SkipMigrations)." -ForegroundColor Gray
}

# Stage 4: FastAPI Backend
Write-Host "[4/6] Starting DocuMind Backend (FastAPI on 127.0.0.1:8000)..." -ForegroundColor Yellow
$backendRunning = $false
$backendPortProc = Get-ProcessByPort -Port 8000
if ($backendPortProc) {
    if (Test-EndpointQuick -Url "http://127.0.0.1:8000/api/v1/health") {
        Write-Host "  Backend is already running on http://127.0.0.1:8000." -ForegroundColor Green
        $backendRunning = $true
    }
    else {
        $procNames = ($backendPortProc | ForEach-Object { "$($_.ProcessName) (PID $($_.Id))" }) -join ", "
        Write-Host "  Warning: Port 8000 is occupied by $procNames but not responding to health check." -ForegroundColor Yellow
    }
}

if (-not $backendRunning) {
    $backendCommand = "& '$pythonExe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir '$backendRoot' --reload"
    Start-DevWindow -Title "DocuMind Backend (FastAPI)" -WorkingDirectory $backendRoot -Command $backendCommand
    Write-Host "  Launched backend server in separate terminal window." -ForegroundColor Green
}

# Stage 5: React Frontend
Write-Host "[5/6] Starting DocuMind Frontend (Vite on 127.0.0.1:5173)..." -ForegroundColor Yellow
$frontendRunning = $false
$frontendPortProc = Get-ProcessByPort -Port 5173
if ($frontendPortProc) {
    if (Test-EndpointQuick -Url "http://127.0.0.1:5173/") {
        Write-Host "  Frontend is already running on http://127.0.0.1:5173." -ForegroundColor Green
        $frontendRunning = $true
    }
    else {
        $procNames = ($frontendPortProc | ForEach-Object { "$($_.ProcessName) (PID $($_.Id))" }) -join ", "
        Write-Host "  Warning: Port 5173 is occupied by $procNames." -ForegroundColor Yellow
    }
}

if (-not $frontendRunning) {
    $frontendCommand = "& npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort"
    Start-DevWindow -Title "DocuMind Frontend (Vite)" -WorkingDirectory $frontendRoot -Command $frontendCommand
    Write-Host "  Launched frontend server in separate terminal window." -ForegroundColor Green
}

# Stage 6: Service Verification & Browser Launch
Write-Host "[6/6] Verifying services and opening browser..." -ForegroundColor Yellow

$backendOk = Wait-ForEndpoint -Url "http://127.0.0.1:8000/api/v1/health" -ServiceName "Backend API" -TimeoutSeconds 30
if (-not $backendOk) {
    # Check openapi as fallback
    $backendOk = Wait-ForEndpoint -Url "http://127.0.0.1:8000/openapi.json" -ServiceName "Backend OpenAPI" -TimeoutSeconds 10
}

$frontendOk = Wait-ForEndpoint -Url "http://127.0.0.1:5173/" -ServiceName "Frontend UI" -TimeoutSeconds 30

if (-not $backendOk) {
    Write-Host ""
    Write-Host "ERROR: Backend did not respond on http://127.0.0.1:8000. Inspect the 'DocuMind Backend' terminal window for errors." -ForegroundColor Red
}

if (-not $frontendOk) {
    Write-Host ""
    Write-Host "ERROR: Frontend did not respond on http://127.0.0.1:5173. Inspect the 'DocuMind Frontend' terminal window for errors." -ForegroundColor Red
}

if ($backendOk -and $frontendOk) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "           DocuMind AI is Running Successfully!             " -ForegroundColor Green
    Write-Host "------------------------------------------------------------" -ForegroundColor Green
    Write-Host "  Frontend UI:  http://127.0.0.1:5173/                      " -ForegroundColor White
    Write-Host "  Backend API:  http://127.0.0.1:8000/docs                  " -ForegroundColor White
    Write-Host "  Database:     PostgreSQL 16 + pgvector (localhost:5432)   " -ForegroundColor White
    Write-Host "------------------------------------------------------------" -ForegroundColor Green
    Write-Host "  Terminal:     Logs are visible in the Backend & Frontend  " -ForegroundColor Gray
    Write-Host "                terminal windows.                           " -ForegroundColor Gray
    Write-Host "  To Stop:      Run .\stop.bat                              " -ForegroundColor Gray
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""

    if (-not $NoBrowser) {
        Open-Browser -Url "http://127.0.0.1:5173/"
    }
}
else {
    throw "One or more DocuMind AI services failed to start. See error messages above."
}
