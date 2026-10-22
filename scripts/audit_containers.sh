#!/usr/bin/env bash
# Audita el endurecimiento de los contenedores de un despliegue con docker compose.
# Uso: scripts/audit_containers.sh   (con COMPOSE_PROJECT_NAME si el proyecto no se llama igual que la carpeta)
# Revisa usuario, capacidades, privilegios, puertos, limites, montajes peligrosos, secretos y entorno.
# Sale con error si alguna comprobacion falla.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
export MSYS_NO_PATHCONV=1
project="${COMPOSE_PROJECT_NAME:-$(basename "$PWD")}"
project="$(echo "$project" | tr '[:upper:]' '[:lower:]')"
failures=0

check() {
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "OK     | ${description}"
  else
    echo "FALLA  | ${description}"
    failures=$((failures + 1))
  fi
}

inspect() { docker inspect -f "$2" "$1"; }

equals() { [ "$(inspect "$1" "$2")" = "$3" ]; }

contains() { inspect "$1" "$2" | grep -q -- "$3"; }

lacks() { ! inspect "$1" "$2" | grep -q -i -E -- "$3"; }

audit_static() {
  local c="$1" name="$2"
  echo "== ${name} (configuracion) =="
  check "${name}: no corre como root" bash -c "u=\$(docker inspect -f '{{.Config.User}}' '$c'); [ -n \"\$u\" ] && [ \"\$u\" != root ] && [ \"\$u\" != 0 ]"
  check "${name}: sin capacidades de Linux (cap_drop ALL)" contains "$c" '{{.HostConfig.CapDrop}}' ALL
  check "${name}: sin capacidades agregadas" equals "$c" '{{.HostConfig.CapAdd}}' '[]'
  check "${name}: no-new-privileges activo" contains "$c" '{{.HostConfig.SecurityOpt}}' no-new-privileges
  check "${name}: no es privilegiado" equals "$c" '{{.HostConfig.Privileged}}' false
  check "${name}: no publica ningun puerto" equals "$c" '{{.HostConfig.PortBindings}}' 'map[]'
  check "${name}: no usa la red del host" lacks "$c" '{{.HostConfig.NetworkMode}}' '^host$'
  check "${name}: limite de memoria definido" bash -c "[ \"\$(docker inspect -f '{{.HostConfig.Memory}}' '$c')\" -gt 0 ]"
  check "${name}: limite de procesos definido" bash -c "[ \"\$(docker inspect -f '{{.HostConfig.PidsLimit}}' '$c')\" -gt 0 ]"
  check "${name}: no monta el socket de Docker" lacks "$c" '{{range .Mounts}}{{.Source}} {{end}}' 'docker.sock'
  check "${name}: sin secretos en variables de entorno" lacks "$c" '{{range .Config.Env}}{{println .}}{{end}}' '^[A-Z_]*(TOKEN|API_KEY|SECRET|PASSWORD)[A-Z_0-9]*=.+'
}

audit_runtime() {
  local name="$1" expected_secrets="$2"
  shift 2
  echo "== ${name} (en ejecucion) =="
  local report
  # shellcheck disable=SC2016  # las expresiones deben evaluarse dentro del contenedor, no aqui
  report="$("$@" sh -c 'echo "uid=$(id -u)"; echo "cap=$(grep CapEff /proc/self/status | cut -f2)"; echo "nnp=$(grep NoNewPrivs /proc/self/status | cut -f2)"; echo "secrets=$(ls /run/secrets 2>/dev/null | sort | tr "\n" " ")"' 2>/dev/null)"
  check "${name}: usuario sin privilegios (uid != 0)" bash -c "echo '$report' | grep -q '^uid=' && ! echo '$report' | grep -q '^uid=0$'"
  check "${name}: capacidades efectivas vacias" bash -c "echo '$report' | grep -q '^cap=0000000000000000$'"
  check "${name}: no_new_privs activo" bash -c "echo '$report' | grep -q '^nnp=1$'"
  check "${name}: solo ve sus propios secretos (${expected_secrets})" bash -c "[ \"\$(echo '$report' | sed -n 's/^secrets=//p' | xargs)\" = '$expected_secrets' ]"
}

resolver="${project}-resolver-1"
bot="${project}-bot-1"
docker compose -p "$project" create --no-recreate bot >/dev/null 2>&1 || true

audit_static "$resolver" resolver
audit_runtime resolver "resolver_api_key_sha256" docker exec "$resolver"
audit_static "$bot" bot
check "bot: sistema de archivos de solo lectura" equals "$bot" '{{.HostConfig.ReadonlyRootfs}}' true
audit_runtime bot "discord_token resolver_api_key" docker compose -p "$project" run --rm --no-deps --entrypoint "" bot

echo
if [ "$failures" -eq 0 ]; then
  echo "Despliegue endurecido: todas las comprobaciones pasaron."
else
  echo "${failures} comprobacion(es) fallaron." >&2
  exit 1
fi
