param(
    [ValidateSet("setup", "resolver", "bot", "test", "lint", "token", "keygen", "audit")]
    [string]$Task = "setup",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Extra
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"

function Assert-Venv {
    if (-not (Test-Path $python)) {
        Write-Error "No existe el entorno virtual. Ejecuta primero: .\scripts\dev.ps1 setup"
    }
}

switch ($Task) {
    "setup" {
        if (-not (Test-Path $python)) { python -m venv .venv }
        & $python -m pip install --upgrade pip
        & $python -m pip install -r requirements-dev.txt
        if (-not (Test-Path ".env")) {
            Copy-Item ".env.example" ".env"
            Write-Host "Se creo .env (sin secretos)."
        }
        Write-Host "Siguiente: .\scripts\dev.ps1 token   y   .\scripts\dev.ps1 keygen"
        if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Warning "FFmpeg no esta en el PATH. Instalalo con: winget install Gyan.FFmpeg"
        }
    }
    "resolver" {
        Assert-Venv
        $env:PYTHONPATH = "services/resolver/src"
        & $python -m resolver.main
    }
    "bot" {
        Assert-Venv
        $env:PYTHONPATH = "services/bot/src"
        & $python -m bot.main
    }
    "token" {
        Assert-Venv
        $env:PYTHONPATH = "services/bot/src;scripts"
        & $python scripts/store_secret.py DISCORD_TOKEN @Extra
    }
    "keygen" {
        Assert-Venv
        $env:PYTHONPATH = "services/bot/src;services/resolver/src;scripts"
        & $python scripts/gen_api_key.py @Extra
    }
    "audit" {
        Assert-Venv
        & $python -m pip_audit --skip-editable
    }
    "test" {
        Assert-Venv
        & $python -m pytest
    }
    "lint" {
        Assert-Venv
        & $python -m ruff check .
        & $python -m ruff format --check .
    }
}
