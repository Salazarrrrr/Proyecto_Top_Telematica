$ErrorActionPreference = "Stop"
$proyecto = Split-Path $PSScriptRoot -Parent
$pythonProyecto = Join-Path $proyecto ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $pythonProyecto) {
    $python = $pythonProyecto
} else {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$envPath = Join-Path $PSScriptRoot ".env"
if (Test-Path -LiteralPath $envPath) {
    throw "Ya existe Deploy/.env. No lo sobrescribo para conservar secretos y llaves existentes."
}

function New-Secret {
    param([int]$Length = 32)
    $bytes = New-Object byte[] $Length
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [Convert]::ToBase64String($bytes)
}

$demoToken = New-Secret
$usuarios = ConvertTo-Json -InputObject @{ demo = $demoToken } -Compress
$passwords = ConvertTo-Json -InputObject @{ admin = (New-Secret); demo = (New-Secret) } -Compress
$roles = ConvertTo-Json -InputObject @{ admin = "admin"; demo = "usuario" } -Compress
$lines = @(
    "DFS_USERS='$usuarios'",
    "DFS_USER_PASSWORDS='$passwords'",
    "DFS_USER_ROLES='$roles'",
    "DFS_AUTH_USERS_FILE=/app/metadata/usuarios.json",
    "DFS_DEFAULT_USER=demo",
    "DFS_ADMIN_TOKEN=$(New-Secret)",
    "DFS_NODE_TOKEN=$(New-Secret)",
    "DFS_NODE1_STORAGE_KEY=$(New-Secret)",
    "DFS_NODE2_STORAGE_KEY=$(New-Secret)",
    "DFS_NODE3_STORAGE_KEY=$(New-Secret)"
)
Set-Content -LiteralPath $envPath -Value $lines -Encoding ascii

try {
    & $python (Join-Path $PSScriptRoot "generar_certificados.py")
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron generar los certificados TLS" }
} catch {
    Remove-Item -LiteralPath $envPath -Force
    throw
}

Write-Host "Configuración de laboratorio creada. Protege Deploy/.env y Deploy/certs/ca.key."
Write-Host "Contraseñas iniciales (cámbialas después del primer inicio):"
Write-Host "  admin: $($passwords | ConvertFrom-Json | Select-Object -ExpandProperty admin)"
Write-Host "  demo:  $($passwords | ConvertFrom-Json | Select-Object -ExpandProperty demo)"
