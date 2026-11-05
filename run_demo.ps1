param(
    [switch]$SkipIsaac,
    [switch]$SkipWeb,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

# The whole project is location independent: everything is resolved from this
# script's folder, so it can be cloned into any directory or user account.
$IsaacRoot = $PSScriptRoot
$WebDir = Join-Path $IsaacRoot "web"
$GreenDir = Join-Path $IsaacRoot "greenair"
$Url = "http://127.0.0.1:8080"

$DataRoot = if ($env:GREENAIR_DATA) { $env:GREENAIR_DATA } else { Join-Path $IsaacRoot "data" }
if (-not [System.IO.Path]::IsPathRooted($DataRoot)) {
    $DataRoot = Join-Path $IsaacRoot $DataRoot
}

$VenvPython = Join-Path $IsaacRoot "venv\Scripts\python.exe"
$VenvPythonW = Join-Path $IsaacRoot "venv\Scripts\pythonw.exe"
$Python = if ($env:GREENAIR_PYTHON) { $env:GREENAIR_PYTHON } elseif (Test-Path $VenvPython) { $VenvPython } else { $null }
$PythonW = if ($env:GREENAIR_PYTHONW) { $env:GREENAIR_PYTHONW } elseif (Test-Path $VenvPythonW) { $VenvPythonW } else { $null }

if (-not $Python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source }
}
if (-not $PythonW) {
    $cmd = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($cmd) { $PythonW = $cmd.Source } else { $PythonW = $Python }
}
if (-not $Python) {
    throw "Python not found. Create a venv in $IsaacRoot\venv or set GREENAIR_PYTHON."
}
if (-not $PythonW) {
    throw "pythonw not found. Set GREENAIR_PYTHONW or create the venv."
}
if (-not (Test-Path $VenvPython) -and -not $env:GREENAIR_PYTHON) {
    Write-Warning "No project venv found; using system Python ($Python)."
    Write-Warning "Install web dependencies: $Python -m pip install -r requirements-web.txt"
    Write-Warning "Isaac Sim launch requires a Python environment where isaacsim is installed."
}

if (-not (Test-Path (Join-Path $DataRoot "industrial_fire\export\metadata.json"))) {
    Write-Warning "Scenario data not found in $DataRoot"
    Write-Warning "If you cloned the repo, run: git lfs pull"
    Write-Warning "Or point GREENAIR_DATA to a folder that contains industrial_fire/, urban_infrastructure_fire/, debris_dust/."
}

function Test-Web {
    try {
        return [bool](Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 2).ok
    } catch {
        return $false
    }
}

if (-not $SkipWeb) {
    $healthy = Test-Web
    if (-not $healthy) {
        Write-Host "[demo] starting web server"
        Start-Process -FilePath $PythonW -ArgumentList "app.py" -WorkingDirectory $WebDir -WindowStyle Hidden
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-Web) { $healthy = $true; break }
        }
    }
    if ($healthy) {
        Write-Host "[demo] web ready at $Url"
    } else {
        Write-Warning "web server did not start; check $WebDir\server_run.log"
    }
}

if (-not $SkipIsaac) {
    $out = Join-Path $GreenDir "captures\live_out.txt"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
    $arg = 'cd /d "' + $GreenDir + '" && "' + $Python + '" app.py > "' + $out + '" 2>&1'
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $arg -WindowStyle Hidden
    Write-Host "[demo] Isaac Sim launching (log: $out)"
}

if (-not $SkipWeb -and -not $NoBrowser) {
    Start-Sleep -Seconds 1
    Start-Process $Url
}

Write-Host ""
Write-Host "Isaac keys: 1 chase | 2 orbit | 3 ground | 4 top | C camera cycle | 5 scene cycle | 7/8/9 scenario | H hud | SPACE pause | R restart | ESC quit"
Write-Host "Project root: $IsaacRoot"
Write-Host "Data root:    $DataRoot"
