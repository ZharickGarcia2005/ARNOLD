$ErrorActionPreference = "Stop"
$arnoldBackend = $PSScriptRoot
$arnoldPython = Join-Path $arnoldBackend ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $arnoldPython)) {
    throw "No se encontró el entorno virtual de ARNOLD."
}
Set-Location -LiteralPath $arnoldBackend
$env:DJANGO_SETTINGS_MODULE = "core.settings.development"
$env:ARNOLD_LOCAL_QUEUE = "1"
& $arnoldPython manage.py check
if ($LASTEXITCODE -ne 0) { throw "La revisión de Django falló." }
$arnoldWorker = Start-Process -FilePath $arnoldPython -ArgumentList @(
    "-u", "manage.py", "process_pending", "--watch"
) -WorkingDirectory $arnoldBackend -WindowStyle Hidden -PassThru
try {
    Write-Host "ARNOLD y su trabajador local están activos. Abre http://127.0.0.1:8000/"
    & $arnoldPython manage.py runserver 127.0.0.1:8000 --noreload
} finally {
    if (-not $arnoldWorker.HasExited) { $arnoldWorker.Kill() }
}
