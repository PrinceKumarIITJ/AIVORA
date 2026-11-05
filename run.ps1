$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create virtual environment' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
Write-Host 'AIVORA: http://127.0.0.1:8090'
& '.\.venv\Scripts\python.exe' -m uvicorn aivora.main:app --host 127.0.0.1 --port 8090
