[CmdletBinding()]
param([switch]$Apply,[switch]$ApproveDatabaseStop,[string]$ProjectRoot='')
$ErrorActionPreference='Stop'
if(-not $ProjectRoot){$ProjectRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path}
$python=Join-Path $ProjectRoot '.venv/Scripts/python.exe'
& $python -B (Join-Path $ProjectRoot 'scripts/prepare_windows_services.py')
if($LASTEXITCODE -ne 0){throw 'No se pudieron preparar las configuraciones.'}
if(-not $Apply){
 Write-Output 'PREVISUALIZACION: dos servicios LocalService, inicio automático diferido, reinicio por fallos y dependencia Attention -> Database.'
 Write-Output 'No se instalaron servicios ni se cambiaron permisos. Revisar .tools/stability/services/*.xml.'
 return
}
foreach($file in @('.tools/stability/services/OpticasAmaruDatabase.exe','.tools/stability/services/OpticasAmaruAttention.exe','.tools/mariadb/local-admin.json','.tools/mariadb/data/my.ini','amaru/.env.qr-demo')){
 if(-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $file))){throw "Falta $file. Preparar primero los archivos locales; no se instala nada."}
}
if(-not $ApproveDatabaseStop){throw 'Se requiere autorizar expresamente la parada breve de MariaDB del proyecto.'}
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Ejecutar como administrador tras la autorización del propietario.'}
$serviceNames=@('OpticasAmaruDatabase','OpticasAmaruAttention')
foreach($serviceName in $serviceNames){if(Get-Service -Name $serviceName -ErrorAction SilentlyContinue){throw "Ya existe $serviceName; revisar antes de reemplazarlo."}}
& $python -B (Join-Path $ProjectRoot 'scripts/backup_attention.py') --env-file (Join-Path $ProjectRoot 'amaru/.env')
if($LASTEXITCODE -ne 0){throw 'Falló el respaldo de la base habitual.'}
& $python -B (Join-Path $ProjectRoot 'scripts/backup_attention.py')
if($LASTEXITCODE -ne 0){throw 'Falló el respaldo de atención.'}
& $python -B (Join-Path $ProjectRoot 'scripts/service_database.py') provision
if($LASTEXITCODE -ne 0){throw 'Falló la preparación del cierre SQL controlado.'}
$directory=Join-Path $ProjectRoot '.tools/stability/services'
foreach($serviceName in $serviceNames){
 & (Join-Path $directory "$serviceName.exe") install
 if($LASTEXITCODE -ne 0){throw "Falló la instalación de $serviceName. No se borran servicios existentes."}
 & sc.exe sidtype $serviceName unrestricted | Out-Null
 if($LASTEXITCODE -ne 0){throw 'No se pudo configurar el SID de servicio.'}
}
function Grant-Scoped([string]$Path,[string]$Identity,[string]$Rights){
 & icacls.exe $Path /grant "${Identity}:$Rights" /Q | Out-Null
 if($LASTEXITCODE -ne 0){throw "No se pudo conceder acceso a $Path"}
}
$ownerSid=(Get-Content (Join-Path $ProjectRoot '.tools/stability/install-owner.json') -Raw | ConvertFrom-Json).sid
if($ownerSid -notmatch '^S-1-5-'){throw 'SID del propietario inválido.'}
function Protect-ProjectItem([string]$Path,[bool]$Directory=$false){
 if(-not (Test-Path -LiteralPath $Path)){return}
 $rights=if($Directory){'(OI)(CI)(F)'}else{'(F)'}
 & icacls.exe $Path /inheritance:r /grant:r "*${ownerSid}:$rights" "*S-1-5-18:$rights" "*S-1-5-32-544:$rights" /Q | Out-Null
 if($LASTEXITCODE -ne 0){throw "No se pudo proteger $Path"}
}
$privateFiles=@('amaru/.env','amaru/.env.r2','amaru/.env.migrations','amaru/.env.qr-demo','amaru/demo-credentials.json','.tools/mariadb/local-admin.json','.tools/attention/demo-credentials.json','.tools/attention/database-readonly.env','.tools/demostracion/database.env','.tools/stability/service-stop.env','.tools/cloudflare/env.normal.before-r2','.tools/cloudflare/env.r2.before')
foreach($relative in $privateFiles){Protect-ProjectItem (Join-Path $ProjectRoot $relative)}
foreach($relative in @('.tools/stability/backups','.tools/mariadb/data')){Protect-ProjectItem (Join-Path $ProjectRoot $relative) $true}
$basePython=& $python -c 'import sys;print(sys.base_prefix)'
foreach($serviceName in $serviceNames){
 $identity="NT SERVICE\$serviceName"
 foreach($relative in @('','.tools','.tools/stability','amaru')){Grant-Scoped (Join-Path $ProjectRoot $relative) $identity '(RX)'}
 foreach($relative in @('.venv','scripts','.tools/stability/services')){Grant-Scoped (Join-Path $ProjectRoot $relative) $identity '(OI)(CI)(RX)'}
 Grant-Scoped $basePython $identity '(OI)(CI)(RX)'
 Grant-Scoped (Join-Path $ProjectRoot '.tools/stability/runtime') $identity '(OI)(CI)(M)'
}
$dbIdentity='NT SERVICE\OpticasAmaruDatabase'
Grant-Scoped (Join-Path $ProjectRoot '.tools/mariadb') $dbIdentity '(RX)'
Grant-Scoped (Join-Path $ProjectRoot '.tools/mariadb/mariadb-11.4.13-winx64') $dbIdentity '(OI)(CI)(RX)'
Grant-Scoped (Join-Path $ProjectRoot '.tools/mariadb/data') $dbIdentity '(OI)(CI)(M)'
Grant-Scoped (Join-Path $ProjectRoot '.tools/stability/service-stop.env') $dbIdentity '(R)'
$webIdentity='NT SERVICE\OpticasAmaruAttention'
foreach($relative in @('amaru/config','amaru/gestion','amaru/static','frontend_amaru')){Grant-Scoped (Join-Path $ProjectRoot $relative) $webIdentity '(OI)(CI)(RX)'}
foreach($relative in @('amaru/serve_attention_stable.py','amaru/.env.qr-demo')){Grant-Scoped (Join-Path $ProjectRoot $relative) $webIdentity '(R)'}
& $python -B (Join-Path $ProjectRoot 'scripts/attention_runtime.py') stop
$stopDeadline=(Get-Date).AddSeconds(45)
while((Get-NetTCPConnection -State Listen -LocalPort 8005 -ErrorAction SilentlyContinue) -and (Get-Date) -lt $stopDeadline){Start-Sleep -Milliseconds 500}
if(Get-NetTCPConnection -State Listen -LocalPort 8005 -ErrorAction SilentlyContinue){throw 'El origen manual aún no se cerró; no se duplica.'}
& $python -B (Join-Path $ProjectRoot 'scripts/service_database.py') stop
if($LASTEXITCODE -ne 0){throw 'MariaDB no se cerró correctamente; no iniciar otra instancia.'}
Start-Service OpticasAmaruDatabase
$deadline=(Get-Date).AddSeconds(45)
while(-not (Get-NetTCPConnection -State Listen -LocalPort 3306 -ErrorAction SilentlyContinue)){
 if((Get-Date) -gt $deadline){throw 'MariaDB no abrió el puerto esperado.'}
 Start-Sleep -Milliseconds 500
}
Start-Service OpticasAmaruAttention
Write-Output 'Servicios instalados. Verificar salud y permisos desde la cuenta de servicio antes de dar la operación por comprobada.'
