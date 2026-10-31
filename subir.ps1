<#
.SYNOPSIS
    Sobe toda a aplicação: containers, API e front-end.

.DESCRIPTION
    Pode rodar de novo a qualquer momento: o que já está no ar é mantido. A API e o front abrem em
    janelas próprias, para deixar os logs à vista; fechar a janela encerra o serviço.

.PARAMETER SemNavegador
    Não abre o navegador no final.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\subir.ps1
#>
param([switch]$SemNavegador)

$ErrorActionPreference = 'Stop'

$raiz = $PSScriptRoot
$pastaApi = Join-Path $raiz 'rag-evaluation-api'
$pastaWeb = Join-Path $raiz 'rag-evaluation-web'
$urlApi = 'http://127.0.0.1:8000/api/health'
$urlWeb = 'http://localhost:4200'

function Parar-ComErro([string]$mensagem) {
    Write-Host "`nERRO: $mensagem" -ForegroundColor Red
    exit 1
}

function Testar-Url([string]$url) {
    try {
        Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch [System.Net.WebException] {
        # A API responde 503 quando algum componente caiu, mas o processo está no ar.
        return $null -ne $_.Exception.Response
    } catch {
        return $false
    }
}

function Aguardar-Url([string]$nome, [string]$url, [int]$limiteSegundos, [string]$dica) {
    Write-Host "  Aguardando $nome..." -NoNewline
    $inicio = Get-Date
    while (-not (Testar-Url $url)) {
        if (((Get-Date) - $inicio).TotalSeconds -gt $limiteSegundos) {
            Write-Host ''
            Parar-ComErro "$nome não respondeu em $limiteSegundos s. $dica"
        }
        Start-Sleep -Seconds 3
    }
    Write-Host " pronto ($([int]((Get-Date) - $inicio).TotalSeconds) s)" -ForegroundColor Green
}

function Abrir-Janela([string]$titulo, [string]$pasta, [string]$comando) {
    $script = "`$Host.UI.RawUI.WindowTitle = '$titulo'; $comando"
    Start-Process powershell -WorkingDirectory $pasta -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $script
}

Write-Host '1/4 Verificando os pré-requisitos' -ForegroundColor Cyan
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Parar-ComErro 'Docker não encontrado. Instale o Docker Desktop.'
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Parar-ComErro 'npm não encontrado. Instale o Node.js 20 ou superior.'
}
$arquivoEnv = Join-Path $pastaApi '.env'
if (-not (Test-Path $arquivoEnv)) {
    Parar-ComErro "Falta $arquivoEnv. Veja a seção 'Variáveis de ambiente da API' no README."
}
if (-not (Select-String -Path $arquivoEnv -Pattern '^CHAT_API_KEY=\S' -Quiet)) {
    Parar-ComErro "Preencha CHAT_API_KEY em $arquivoEnv."
}

# Native commands escrevem progresso no stderr; com 'Stop', isso viraria exceção no PowerShell 5.1.
$ErrorActionPreference = 'Continue'
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerDesktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $dockerDesktop)) {
        Parar-ComErro 'O Docker não está respondendo. Abra o Docker Desktop e tente de novo.'
    }
    Write-Host '  Abrindo o Docker Desktop...' -NoNewline
    Start-Process $dockerDesktop
    $inicio = Get-Date
    do {
        if (((Get-Date) - $inicio).TotalSeconds -gt 180) {
            Write-Host ''
            Parar-ComErro 'O Docker não respondeu em 180 s. Confira o Docker Desktop e tente de novo.'
        }
        Start-Sleep -Seconds 3
        docker info *> $null
    } while ($LASTEXITCODE -ne 0)
    Write-Host ' pronto' -ForegroundColor Green
}

Write-Host '2/4 Subindo os containers' -ForegroundColor Cyan
Push-Location $pastaApi
docker compose up -d *> $null
$saidaCompose = $LASTEXITCODE
Pop-Location
if ($saidaCompose -ne 0) {
    Parar-ComErro "docker compose falhou. Rode 'docker compose up -d' em $pastaApi para ver o erro."
}
$ErrorActionPreference = 'Stop'

# Limites folgados: na primeira vez, o reordenador ainda baixa 2,2 GB antes de carregar.
Aguardar-Url 'Milvus' 'http://localhost:9091/healthz' 300 'Veja: docker logs rag-milvus'
Aguardar-Url 'Docling' 'http://localhost:5001/health' 300 'Veja: docker logs rag-docling'
Aguardar-Url 'Reordenador' 'http://localhost:8081/health' 900 'Veja: docker logs rag-reranker'

Write-Host '3/4 Subindo a API' -ForegroundColor Cyan
if (Testar-Url $urlApi) {
    Write-Host '  Já está no ar: mantida. Reinicie-a se o .env mudou.' -ForegroundColor Yellow
} else {
    $fastapi = Join-Path $pastaApi '.venv\Scripts\fastapi.exe'
    if (-not (Test-Path $fastapi)) {
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Parar-ComErro "Ambiente da API não instalado e 'uv' não encontrado. Rode 'pip install uv' e tente de novo."
        }
        Write-Host '  Instalando as dependências da API...'
        Push-Location $pastaApi
        uv sync
        $saidaUv = $LASTEXITCODE
        Pop-Location
        if ($saidaUv -ne 0) {
            Parar-ComErro 'uv sync falhou.'
        }
    }
    # Sem o UTF-8, o banner do FastAPI quebra no console do Windows.
    Abrir-Janela 'RAG - API' $pastaApi "`$env:PYTHONIOENCODING = 'utf-8'; & '$fastapi' dev"
    Aguardar-Url 'API' $urlApi 120 'Veja o erro na janela "RAG - API".'
}

Write-Host '4/4 Subindo o front-end' -ForegroundColor Cyan
if (Testar-Url $urlWeb) {
    Write-Host '  Já está no ar: mantido.' -ForegroundColor Yellow
} else {
    $comandoWeb = 'npm start'
    if (-not (Test-Path (Join-Path $pastaWeb 'node_modules'))) {
        $comandoWeb = 'npm install; npm start'
    }
    Abrir-Janela 'RAG - Web' $pastaWeb $comandoWeb
    Aguardar-Url 'Front-end' $urlWeb 300 'Veja o erro na janela "RAG - Web".'
}

Write-Host "`nTudo no ar." -ForegroundColor Green
Write-Host "  Avaliador:     $urlWeb"
Write-Host "  Gerenciamento: $urlWeb/admin"
Write-Host '  Swagger:       http://127.0.0.1:8000/docs'

if (-not $SemNavegador) {
    Start-Process "$urlWeb/admin"
}
