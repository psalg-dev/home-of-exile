# Start frontend and backend, killing any existing instances first

$BackendPort = 8000
$FrontendPort = 5173

Write-Host "Stopping any processes on ports $BackendPort and $FrontendPort..."

foreach ($port in @($BackendPort, $FrontendPort)) {
    $procIds = netstat -ano | Select-String ":$port\s" | ForEach-Object {
        ($_ -split '\s+')[-1]
    } | Sort-Object -Unique
    foreach ($procId in $procIds) {
        if ($procId -match '^\d+$' -and $procId -ne '0') {
            Write-Host "  Killing PID $procId (port $port)"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

Start-Sleep -Seconds 1

$docker = Get-Command docker -ErrorAction SilentlyContinue
$luajit = Get-Command luajit -ErrorAction SilentlyContinue

$useDockerBackend = $false
if (-not $luajit -and $docker) {
    $useDockerBackend = $true
}

if ($useDockerBackend) {
    Write-Host "LuaJIT not found locally; starting backend via docker compose (db + backend)..."
    try {
        docker compose up -d db backend | Out-Null
    }
    catch {
        Write-Host "  Could not start backend via docker compose; falling back to local backend."
        $useDockerBackend = $false
    }
}

if (-not $useDockerBackend) {
    if ($docker) {
        Write-Host "Ensuring PostgreSQL container is running (docker compose up -d db)..."
        try {
            docker compose up -d db | Out-Null
        }
        catch {
            Write-Host "  Could not start db via docker compose; continuing without DB."
        }
    }
    else {
        Write-Host "Docker not found; continuing without auto-starting PostgreSQL."
    }

    # Load .env variables into the environment so the backend process inherits them.
    $dotEnv = Join-Path $PSScriptRoot ".env"
    if (Test-Path $dotEnv) {
        Get-Content $dotEnv | Where-Object { $_ -match "^\s*[^#]\S+=.+" } | ForEach-Object {
            $kv = $_ -split "=", 2
            $k = $kv[0].Trim(); $v = $kv[1].Trim()
            [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
        }
        Write-Host "  Loaded .env ($dotEnv)"
    }

    # Build env-var forwarding string for the new window.
    $envFwd = ""
    @("OPENAI_API_KEY","DATABASE_URL","POE_NINJA_LEAGUE","LUAJIT_POOL_SIZE") | ForEach-Object {
        $val = [System.Environment]::GetEnvironmentVariable($_, "Process")
        if ($val) { $envFwd += "`$env:$_ = '$val'; " }
    }

    Write-Host "Starting backend (local uvicorn)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "${envFwd}cd '$PSScriptRoot\backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port $BackendPort"
}
else {
    Write-Host "Starting backend (docker compose service)..."
}

Write-Host "Starting frontend..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev"

Write-Host "Done. Backend on http://localhost:$BackendPort  |  Frontend on http://localhost:$FrontendPort"
