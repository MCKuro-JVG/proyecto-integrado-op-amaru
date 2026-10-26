$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Cree .venv e instale amaru/requirements.txt según README.md.' }
# Solo iniciar la instancia portable de este proyecto; no detener servicios existentes.
$databaseConfig = Join-Path $PSScriptRoot '.tools\mariadb\data\my.ini'
$databaseBinary = Join-Path $PSScriptRoot '.tools\mariadb\mariadb-11.4.13-winx64\bin\mariadbd.exe'
if ((Test-Path -LiteralPath $databaseConfig) -and !(Get-NetTCPConnection -LocalPort 3306 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $databaseBinary -ArgumentList ('--defaults-file="' + $databaseConfig + '"') -WindowStyle Hidden
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if (Get-NetTCPConnection -LocalPort 3306 -State Listen -ErrorAction SilentlyContinue) { break }
        Start-Sleep -Milliseconds 500
    }
}
& $python -B amaru/manage.py check --database default
if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar el backend. Revise MariaDB y amaru/.env.' }
Write-Host 'Aplicación: http://127.0.0.1:8001/app/ - Ctrl+C para detener Django.'
& $python -B amaru/manage.py runserver 127.0.0.1:8001
