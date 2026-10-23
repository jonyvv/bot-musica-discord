#!/usr/bin/env bash
# Endurece un servidor Ubuntu 24.04 para correr el bot. Ejecutar UNA vez, como root.
#
# Uso: sudo deploy/harden-host.sh [--dry-run] [--ssh-from CIDR] [--only paso[,paso...]]
#   --dry-run       muestra lo que haria sin tocar nada
#   --ssh-from CIDR limita SSH a esa red (por ejemplo 203.0.113.7/32); recomendado
#   --only          pasos: updates, ssh, firewall, fail2ban, docker, sysctl (por defecto, todos)
#
# Antes de desactivar las contrasenas de SSH verifica que haya una clave autorizada,
# para no dejarte afuera del servidor. Mantene abierta tu sesion actual hasta probar otra nueva.
set -euo pipefail

dry_run=0
ssh_from=""
only="updates,ssh,firewall,fail2ban,docker,sysctl"
root="${TARGET_ROOT:-}"

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=1 ;;
    --ssh-from)
      ssh_from="${2:?--ssh-from necesita una red CIDR}"
      shift
      ;;
    --only)
      only="${2:?--only necesita una lista de pasos}"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Opcion desconocida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ "$dry_run" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  echo "Ejecutalo como root (sudo)." >&2
  exit 1
fi

run() {
  if [ "$dry_run" -eq 1 ]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

write_file() {
  local path="${root}$1" mode="$2" content
  content="$(cat)"
  if [ "$dry_run" -eq 1 ]; then
    echo "[dry-run] escribiria ${path} (modo ${mode}):"
    while IFS= read -r line; do
      echo "    | ${line}"
    done <<<"$content"
    return
  fi
  mkdir -p "$(dirname "$path")"
  printf '%s\n' "$content" >"$path"
  chmod "$mode" "$path"
}

wants() { [[ ",${only}," == *",$1,"* ]]; }

step_updates() {
  echo "== Actualizaciones de seguridad automaticas =="
  run apt-get update -y
  run apt-get upgrade -y
  run apt-get install -y unattended-upgrades ca-certificates
  write_file /etc/apt/apt.conf.d/20auto-upgrades 644 <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
  write_file /etc/apt/apt.conf.d/52bot-unattended 644 <<'EOF'
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF
}

authorized_keys_present() {
  local file
  for file in "${root}"/home/*/.ssh/authorized_keys; do
    if [ -s "$file" ]; then
      return 0
    fi
  done
  return 1
}

step_ssh() {
  echo "== SSH: solo claves, sin root =="
  if [ "$dry_run" -eq 0 ] && ! authorized_keys_present; then
    echo "Ningun usuario normal (no root) tiene una clave en authorized_keys: como se desactiva el" >&2
    echo "acceso de root y de contrasenas, quedarias afuera. Crea un usuario con tu clave publica" >&2
    echo "y volve a ejecutar este paso desde ese usuario con sudo." >&2
    exit 1
  fi
  write_file /etc/ssh/sshd_config.d/99-hardening.conf 644 <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
PermitEmptyPasswords no
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
EOF
  if [ "$dry_run" -eq 0 ]; then
    sshd -t
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  else
    echo "[dry-run] sshd -t && systemctl reload ssh"
  fi
}

step_firewall() {
  echo "== Firewall del host (segunda capa; la primera es la lista de seguridad de Oracle) =="
  run apt-get install -y ufw
  run ufw default deny incoming
  run ufw default allow outgoing
  if [ -n "$ssh_from" ]; then
    run ufw limit from "$ssh_from" to any port 22 proto tcp
  else
    echo "AVISO: SSH queda abierto a todo internet. Usa --ssh-from con tu IP para limitarlo." >&2
    run ufw limit 22/tcp
  fi
  run ufw --force enable
}

step_fail2ban() {
  echo "== fail2ban contra fuerza bruta en SSH =="
  run apt-get install -y fail2ban
  write_file /etc/fail2ban/jail.d/sshd.local 644 <<'EOF'
[sshd]
enabled = true
maxretry = 3
findtime = 10m
bantime = 1h
EOF
  run systemctl enable --now fail2ban
}

step_docker() {
  echo "== Docker (paquetes de Ubuntu, sin scripts descargados de internet) =="
  run apt-get install -y docker.io docker-compose-v2
  if [ -e "${root}/etc/docker/daemon.json" ]; then
    echo "AVISO: /etc/docker/daemon.json ya existe; no se sobrescribe. Revisalo a mano." >&2
  else
    write_file /etc/docker/daemon.json 644 <<'EOF'
{
  "no-new-privileges": true,
  "live-restore": true,
  "userland-proxy": false,
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
  fi
  run systemctl enable --now docker
  run systemctl restart docker
}

step_sysctl() {
  echo "== Parametros de red del kernel =="
  write_file /etc/sysctl.d/99-hardening.conf 644 <<'EOF'
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
EOF
  run sysctl --system
}

for step in updates ssh firewall fail2ban docker sysctl; do
  if wants "$step"; then
    "step_${step}"
  fi
done

cat <<'EOF'

Hecho. Siguientes pasos:
  1. Abri OTRA sesion SSH y comproba que entras antes de cerrar la actual.
  2. Crea los secretos:   deploy/create-secrets.sh
  3. Levanta el bot:      sudo docker compose up -d --build
  4. Verifica:            sudo scripts/audit_containers.sh
EOF
