#!/usr/bin/env bash
# Crea los secretos de Docker del despliegue sin dejar el token en pantalla ni en el historial.
# Uso: deploy/create-secrets.sh [carpeta]     (por defecto ./secrets)
#   FORCE=1 regenera la clave del resolver y vuelve a pedir el token.
# Genera: discord_token, resolver_api_key (la usa el bot) y resolver_api_key_sha256 (la usa el resolver).
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
dir="${1:-secrets}"
container_uid=10001
token_shape='^[A-Za-z0-9_-]{23,}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}$'

umask 077
mkdir -p "$dir"

if [ ! -s "$dir/resolver_api_key" ] || [ "${FORCE:-}" = 1 ]; then
  key="$(openssl rand -base64 72 | tr -d '\n=+/' | cut -c1-48)"
  printf '%s' "$key" >"$dir/resolver_api_key"
  printf '%s' "$key" | sha256sum | cut -d' ' -f1 | tr -d '\n' >"$dir/resolver_api_key_sha256"
  unset key
  echo "Clave del resolver generada."
else
  echo "La clave del resolver ya existe (FORCE=1 para regenerarla)."
fi

if [ ! -s "$dir/discord_token" ] || [ "${FORCE:-}" = 1 ]; then
  read -r -s -p "DISCORD_TOKEN (no se muestra): " token
  echo
  if ! [[ "$token" =~ $token_shape ]]; then
    echo "Eso no parece un token de Discord (formato xxx.yyy.zzz); no se guardo nada." >&2
    exit 1
  fi
  printf '%s' "$token" >"$dir/discord_token"
  unset token
  echo "Token guardado."
else
  echo "El token ya existe (FORCE=1 para reemplazarlo)."
fi

if [ "$(uname -s)" = "Linux" ]; then
  owner="${container_uid}:${container_uid}"
  if [ "$(id -u)" -eq 0 ]; then
    chown "$owner" "$dir"/*
  else
    sudo chown "$owner" "$dir"/*
  fi
fi
chmod 400 "$dir"/* 2>/dev/null || sudo chmod 400 "$dir"/*
echo "Listo: $dir (solo lectura, propiedad del usuario del contenedor)."
