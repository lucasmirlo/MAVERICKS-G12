# Arranque local de un solo comando: PostgreSQL local (.pgdata, puerto 5433), migraciones, frontend, worker y web.
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1            (http://localhost:8000)
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Build     (recompila el frontend)
# Requisitos: Python 3.13 con .venv (pip install -r requirements-dev.txt), Node 24, PostgreSQL 16+ instalado,
# internet para JEV y, opcionalmente, Ollama corriendo en Windows (http://localhost:11434).
param(
    [switch]$Build,
    [int]$Port = 8000,
    [int]$PgPort = 5433
)
# Continue: PowerShell 5 trata como error lo que los comandos nativos (alembic, npm) escriben en stderr.
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { throw "Falta .venv. Ejecuta: python -m venv .venv; .venv\Scripts\python -m pip install -r requirements-dev.txt" }
if (-not (Test-Path (Join-Path $Root '.env'))) { throw "Falta .env. Copia .env.example a .env y rellena TYPESAFE_API_KEY, ADMIN_PASSWORD y SESSION_SECRET." }

# 1. PostgreSQL local en .pgdata
$PgBin = $env:PG_BIN
if (-not $PgBin) {
    $cand = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue | Sort-Object { [int]($_.Name -replace '\D', '') } -Descending | Select-Object -First 1
    if ($cand) { $PgBin = Join-Path $cand.FullName 'bin' }
}
if (-not $PgBin -or -not (Test-Path (Join-Path $PgBin 'pg_ctl.exe'))) { throw "No encuentro PostgreSQL. Define PG_BIN con la carpeta bin de PostgreSQL." }
$PgData = Join-Path $Root '.pgdata'
if (-not (Test-Path $PgData)) {
    Write-Host '[db] Creando clúster local en .pgdata'
    & (Join-Path $PgBin 'initdb.exe') -D $PgData -U srr -A trust -E UTF8 --locale=C | Out-Null
}
& (Join-Path $PgBin 'pg_isready.exe') -h localhost -p $PgPort -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "[db] Arrancando PostgreSQL en el puerto $PgPort"
    # Sin tuberías: el postmaster heredaría el handle y PowerShell esperaría indefinidamente.
    Start-Process -FilePath (Join-Path $PgBin 'pg_ctl.exe') -ArgumentList '-D', "`"$PgData`"", '-o', "`"-p $PgPort`"", '-l', "`"$(Join-Path $Root '.pg.log')`"", 'start' -WindowStyle Hidden
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        & (Join-Path $PgBin 'pg_isready.exe') -h localhost -p $PgPort -q
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL no arrancó; revisa .pg.log" }
}
$exists = & (Join-Path $PgBin 'psql.exe') -h localhost -p $PgPort -U srr -d postgres -tAc "select 1 from pg_database where datname='srr'"
if ($exists -ne '1') { & (Join-Path $PgBin 'createdb.exe') -h localhost -p $PgPort -U srr srr }

# 2. Migraciones
Write-Host '[db] alembic upgrade head'
& $Py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las migraciones.' }

# 3. Frontend compilado servido por la web
if ($Build -or -not (Test-Path (Join-Path $Root 'static\index.html'))) {
    Write-Host '[web] Compilando frontend'
    Push-Location (Join-Path $Root 'frontend')
    if (-not (Test-Path 'node_modules')) { npm ci --no-audit --no-fund }
    npm run build
    Pop-Location
    if (Test-Path (Join-Path $Root 'static')) { Remove-Item -Recurse -Force (Join-Path $Root 'static') }
    Copy-Item -Recurse (Join-Path $Root 'frontend\dist') (Join-Path $Root 'static')
}

# 4. Ollama (opcional): sin él la app funciona en modo regla + JEV
try {
    $v = Invoke-RestMethod -Uri 'http://localhost:11434/api/version' -TimeoutSec 3
    Write-Host "[llm] Ollama $($v.version) disponible"
} catch {
    Write-Host '[llm] Ollama no responde: la app funcionará sin segunda opinión (LLM_PROVIDER efectivo = none).' -ForegroundColor Yellow
}

# 5. Worker en segundo plano y web en primer plano
$WorkerLog = Join-Path $Root 'worker.log'
$worker = Start-Process -FilePath $Py -ArgumentList '-m', 'app.worker' -WorkingDirectory $Root -RedirectStandardOutput $WorkerLog -RedirectStandardError (Join-Path $Root 'worker.err.log') -PassThru -WindowStyle Hidden
Write-Host "[worker] PID $($worker.Id), log en worker.log"
try {
    Write-Host "[web] http://localhost:$Port  (Ctrl+C para parar web y worker)"
    & $Py -m uvicorn app.main:app --host 127.0.0.1 --port $Port
} finally {
    if (-not $worker.HasExited) { Stop-Process -Id $worker.Id -Force -ErrorAction SilentlyContinue }
    Write-Host '[worker] detenido'
}
