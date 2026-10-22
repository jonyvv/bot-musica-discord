#!/usr/bin/env bash
# Lanza los ataques de prueba contra el resolver de un despliegue con docker compose.
# Uso: scripts/attack_compose.sh [--offline] [grupo ...]
#   --offline  no depende de YouTube (para CI o servidores cuya IP YouTube bloquea)
#   grupos     recon injection abuse_input flood bruteforce slowloris heavy legit (por defecto, todos)
# Requiere el despliegue levantado y secrets/resolver_api_key. Sale con error si algun ataque prospera.
set -euo pipefail

cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
project="${COMPOSE_PROJECT_NAME:-bot-musica-discord}"
network="${project}_default"
image="${ATTACK_IMAGE:-${project}-bot}"
offline=()
if [ "${1:-}" = "--offline" ]; then
  offline=(--offline)
  shift
fi
if [ "$#" -gt 0 ]; then
  groups=("$@")
elif [ "${#offline[@]}" -gt 0 ]; then
  groups=(recon injection abuse_input flood bruteforce slowloris)
else
  groups=(recon injection abuse_input flood bruteforce slowloris heavy legit)
fi
root="$(pwd -W 2>/dev/null || pwd)"

wait_healthy() {
  for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "${project}-resolver-1" 2>/dev/null || true)"
    [ "$status" = "healthy" ] && return 0
    sleep 1
  done
  echo "El resolver no llego a estar saludable" >&2
  return 1
}

failed=0
for group in "${groups[@]}"; do
  docker compose -p "$project" restart resolver >/dev/null 2>&1
  wait_healthy
  echo "== ${group} =="
  if ! docker run --rm --network "$network" \
    -v "${root}/scripts:/atk:ro" -v "${root}/secrets/resolver_api_key:/key:ro" \
    "$image" python /atk/attack_resolver.py --key-file /key --only "$group" "${offline[@]}"; then
    failed=$((failed + 1))
  fi
done

echo
if [ "$failed" -eq 0 ]; then
  echo "Todos los grupos de ataque fueron defendidos."
else
  echo "${failed} grupo(s) con ataques exitosos." >&2
  exit 1
fi
