param(
    [ValidateSet("setup", "resolver", "bot", "test", "lint")]
    [string]$Task = "setup"
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
            Write-Host "Se creo .env: completa DISCORD_TOKEN antes de iniciar el bot."
        }
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
