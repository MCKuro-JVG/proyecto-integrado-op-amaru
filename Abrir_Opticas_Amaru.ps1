$ErrorActionPreference = 'Stop'
$taskUrl = 'http://127.0.0.1:8000/'
$taskOnline = $false
$taskResponse = $null
try {
    $taskResponse = Invoke-WebRequest -Uri $taskUrl -UseBasicParsing -TimeoutSec 2
    $taskOnline = $taskResponse.Content -match 'data-page="index"' -and $taskResponse.Content -match 'js/app.js'
    if (-not $taskOnline) { throw 'El puerto 8000 está ocupado por otra página.' }
} catch {
    if ($taskResponse) { throw }
}
if (-not $taskOnline) {
    # El acceso directo debe funcionar aunque Python no este en PATH.
    $taskCandidates = @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
    $taskPythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($taskPythonCommand) { $taskCandidates += $taskPythonCommand.Source }
    $taskPythonInstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path -LiteralPath $taskPythonInstallRoot) {
        $taskCandidates += Get-ChildItem -LiteralPath $taskPythonInstallRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'python.exe' }
    }
    $taskCandidates += Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $taskPython = $null
    foreach ($taskCandidate in ($taskCandidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $taskCandidate -PathType Leaf) {
            try {
                & $taskCandidate -c 'import http.server' 2>$null
                if ($LASTEXITCODE -eq 0) { $taskPython = $taskCandidate; break }
            } catch { }
        }
    }
    if (-not $taskPython) { throw 'No se encontro un Python operativo para iniciar Amaru. Revisa la instalacion de Python o el entorno .venv.' }
    $taskServer = Join-Path $PSScriptRoot 'servidor_amaru.py'
    $taskArguments = '"{0}" --port 8000' -f $taskServer
    $taskLogDirectory = Join-Path $PSScriptRoot 'logs'
    New-Item -ItemType Directory -Path $taskLogDirectory -Force | Out-Null
    Start-Process -FilePath $taskPython -ArgumentList $taskArguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskLogDirectory 'amaru-servidor.log') -RedirectStandardError (Join-Path $taskLogDirectory 'amaru-servidor-error.log')
    for ($taskAttempt = 0; $taskAttempt -lt 20; $taskAttempt++) {
        Start-Sleep -Milliseconds 250
        try {
            $taskResponse = Invoke-WebRequest -Uri $taskUrl -UseBasicParsing -TimeoutSec 2
            if ($taskResponse.StatusCode -eq 200 -and $taskResponse.Content -match 'data-page="index"') { $taskOnline = $true; break }
        } catch { }
    }
    if (-not $taskOnline) { throw 'No se pudo iniciar la pagina local en el puerto 8000. Revisa logs\amaru-servidor-error.log.' }
}
$taskChromePaths = @(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
)
$taskChrome = $taskChromePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($taskChrome) {
    Start-Process -FilePath $taskChrome -ArgumentList $taskUrl
} else {
    Start-Process $taskUrl
}
