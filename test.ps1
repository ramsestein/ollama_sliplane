param(
    [string]$BaseUrl = "https://ollama-sliplane.sliplane.app",
    [string]$Model = "",
    [string]$Prompt = "Responde en una sola frase: que es Ollama?"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "    [FALLO] $msg" -ForegroundColor Red }

$BaseUrl = $BaseUrl.TrimEnd('/')

# 1. Version del servidor
Write-Step "1/3 - Version del servidor ($BaseUrl/api/version)"
try {
    $version = Invoke-RestMethod -Uri "$BaseUrl/api/version" -Method Get -TimeoutSec 30
    Write-Ok "Ollama responde, version: $($version.version)"
}
catch {
    Write-Fail "No se pudo contactar con el servidor: $($_.Exception.Message)"
    exit 1
}

# 2. Modelos disponibles
Write-Step "2/3 - Modelos disponibles ($BaseUrl/api/tags)"
try {
    $tags = Invoke-RestMethod -Uri "$BaseUrl/api/tags" -Method Get -TimeoutSec 60
    $names = @($tags.models | ForEach-Object { $_.name })
    if ($names.Count -eq 0) {
        Write-Fail "No hay modelos cargados todavia. Espera a que termine la descarga inicial."
        exit 1
    }
    Write-Ok "Modelos disponibles: $($names -join ', ')"
}
catch {
    Write-Fail "Error listando modelos: $($_.Exception.Message)"
    exit 1
}

# Elegir modelo
if (-not $Model) {
    $Model = $names[0]
    Write-Host "    Usando el primer modelo disponible: $Model"
}

# 3. Inferencia
Write-Step "3/3 - Generando respuesta ($BaseUrl/v1/chat/completions, modelo: $Model)"
$body = @{
    model    = $Model
    messages = @(@{ role = "user"; content = $Prompt })
    stream   = $false
} | ConvertTo-Json -Depth 5

try {
    $resp = Invoke-RestMethod -Uri "$BaseUrl/v1/chat/completions" -Method Post `
        -Body $body -ContentType "application/json" -TimeoutSec 300
    $answer = $resp.choices[0].message.content
    Write-Ok "Respuesta:"
    Write-Host "    $answer"
}
catch {
    Write-Fail "Error en la inferencia: $($_.Exception.Message)"
    exit 1
}

Write-Host "`nTodo correcto. El endpoint funciona." -ForegroundColor Green
