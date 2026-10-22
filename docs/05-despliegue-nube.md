# Despliegue en la nube (Oracle Cloud Always Free)

Guía para publicar el bot en una VM con la mayor seguridad práctica y costo cero.

## Modelo de amenazas

| Superficie | Estado |
|---|---|
| Puertos de entrada desde internet | **Ninguno** salvo SSH, y SSH limitado a tu IP |
| API del resolver | No publicada: solo el bot la alcanza dentro de la red de Docker, y exige clave |
| Token de Discord y clave | Archivos de secreto (no variables de entorno), propiedad del usuario del contenedor |
| Cookies de YouTube | Solo las ve el resolver |
| Servidores de Discord | El bot se retira solo de cualquier servidor que no esté en la lista permitida |

Como no hay servicios expuestos, los ataques por red (inundación, Slowloris, inyección) solo podrían
venir de un contenedor ya comprometido dentro de la VM. Aun así están cubiertos y probados
(ver [04-seguridad.md](04-seguridad.md)).

## Qué está verificado y qué no

**Verificado en un Docker real (Docker Desktop), con las mismas imágenes y el mismo compose:**

- Las dos imágenes se construyen; corren sin root, sin capacidades y con `no-new-privileges`.
- `scripts/audit_containers.sh`: 30 comprobaciones de endurecimiento, y se comprobó que **falla**
  cuando se despliega mal a propósito (root, puerto publicado, capacidad extra, token en el entorno).
- `scripts/attack_compose.sh`: 78 ataques de prueba contra el resolver desplegado, 0 exitosos.
- `scripts/smoke_playback.py`: FFmpeg decodifica audio real de YouTube y de Spotify dentro del
  contenedor del bot (las 5 canciones de la playlist de prueba).
- La integración bot ↔ resolver con secretos reales montados en `/run/secrets`.
- `deploy/harden-host.sh`: el paso de SSH ejecutado de verdad en un Ubuntu 24.04 limpio
  (`sshd -t` válido y se niega a correr sin una clave autorizada). El resto en `--dry-run`.
- CI en GitHub: tests, auditoría de dependencias, escaneo de imágenes, auditoría y ataques.

**NO verificado, y es tu primer paso en la VM:**

1. **La IP de Oracle frente a YouTube.** Desde IPs de datacenter YouTube suele pedir verificación
   anti-bot. Esto solo se sabe probando: hacelo antes de invertir más (ver paso 7).
2. **`harden-host.sh` completo** (`ufw`, `fail2ban`, instalación de Docker, `unattended-upgrades`):
   requieren un host real con systemd. Están en `--dry-run` y revisados con `shellcheck`.
3. **Imágenes ARM64.** Se probaron en x86-64. Construilas en la propia VM ARM (`docker compose build`)
   y corré `scripts/audit_containers.sh` y `smoke_playback.py` ahí.
4. **El bot contra un servidor de Discord real**, que necesita tu token.

## Pasos

### 1. Cuenta de Oracle

- Activá **MFA** en la cuenta apenas se cree.
- **No la subas a *Pay as you go***: según la documentación de Oracle, una cuenta Always Free sin
  mejorar no puede generar cargos (confirmalo en tu consola; yo no tengo acceso a tu cuenta).
- Creá una alerta de presupuesto (por ejemplo, 1 USD) como red de seguridad.
- La *home region* se elige una vez y no se puede cambiar. Si no hay capacidad ARM (`Out of host
  capacity`), reintentá o usá la instancia AMD `E2.1.Micro` como plan B (1 GB de RAM: agregá swap).

### 2. Red

En la VCN, la **lista de seguridad** de la subred:

| Dirección | Regla |
|---|---|
| Entrada | **Solo TCP 22 desde `TU.IP/32`**. Nada más |
| Salida | Permitir todo (el bot necesita Discord, YouTube y Spotify) |

Esta es la primera capa de firewall; la del host es la segunda.

### 3. Instancia

- Forma `VM.Standard.A1.Flex`, 1 OCPU y 3 GB, imagen **Ubuntu 24.04**. Oracle da hasta 2 OCPU y 12 GB
  en total, pero con poca memoria el uso supera el 20 % y la instancia no se considera inactiva (ver
  *Reclamo por inactividad*).
- Clave SSH `ed25519` generada en tu PC (`ssh-keygen -t ed25519`). **La clave privada nunca va al
  repositorio**: el `.gitignore` ya excluye `*.pem`, `*.key`, `id_*` y `.ssh/`.

### 4. Endurecer el host

```bash
git clone https://github.com/jonyvv/bot-musica-discord.git /opt/bot-musica-discord
cd /opt/bot-musica-discord
sudo deploy/harden-host.sh --dry-run --ssh-from TU.IP/32     # primero mirá qué hará
sudo deploy/harden-host.sh --ssh-from TU.IP/32
```

**No cierres tu sesión SSH** hasta abrir otra y comprobar que entrás. El script se niega a desactivar
las contraseñas si no hay una clave autorizada, para no dejarte afuera.

### 5. Secretos

```bash
deploy/create-secrets.sh                # genera la clave del resolver y pide el token sin mostrarlo
echo "DISCORD_GUILD_ID=ID_DE_TU_SERVIDOR" > .env
mkdir -p data/cookies && sudo chown 10001 data/cookies
```

El token queda en `secrets/discord_token` (modo 400, propiedad del usuario 10001 del contenedor). No
pasa por variables de entorno, así que no aparece en `docker inspect`.

### 6. Levantar

```bash
sudo docker compose up -d --build
sudo scripts/audit_containers.sh        # debe terminar en "Despliegue endurecido"
sudo scripts/attack_compose.sh          # debe terminar en "Todos los grupos de ataque fueron defendidos"
```

### 7. Probar YouTube desde esta IP (el paso decisivo)

```bash
sudo docker compose run --rm --no-deps -v "$PWD/scripts:/atk:ro" -e PYTHONPATH=/app/src:/atk \
  --entrypoint python bot /atk/smoke_playback.py "https://open.spotify.com/playlist/TU_ID" --limit 5
```

Si da errores `bot_detected`, ver la sección 9.3 de [01-requisitos.md](01-requisitos.md) y
[03-setup.md](03-setup.md) (cookies de una cuenta descartable). Si nada funciona, la alternativa es
correr el bot en tu PC cuando lo vayan a usar.

### 8. Discord

- En el portal de desarrolladores, **desactivá *Public Bot*** para que nadie más pueda invitarlo.
- Invitalo con solo los permisos mínimos (ver [03-setup.md](03-setup.md)). Nunca `Administrator`.
- El bot ya se retira solo de servidores no permitidos y avisa en el log si le dieron permisos de más.

## Operación

| Tarea | Cómo |
|---|---|
| Ver estado | `sudo docker compose ps` (el resolver tiene *healthcheck*) |
| Ver logs | `sudo docker compose logs -f --tail 100` (rotan solos: 3 × 10 MB) |
| Actualizar | `git pull && sudo docker compose up -d --build`, luego `audit_containers.sh` |
| `yt-dlp` | Se actualiza solo cada 24 h y reinicia el resolver. **Después de cada versión nueva, corré `smoke_playback.py`**: YouTube cambia qué clientes FFmpeg puede leer |
| Dependencias | Dependabot abre PRs semanales (Python, Docker y Actions); CI las valida |
| Cookies | Caducan: renovarlas es mantenimiento periódico |

### Reclamo por inactividad

Según la documentación de Oracle, una instancia Always Free se considera inactiva, y puede ser
reclamada, si durante 7 días el CPU (percentil 95) y la red están bajo el 20 %, y en las ARM también la
memoria. Un bot de música ocioso cumple lo primero. Por eso la instancia ARM lleva poca memoria: así el
uso supera el 20 %. Es una mitigación, no una garantía; mirá las métricas de la instancia tras unos días.

Si Oracle la reclama, el despliegue se reconstruye con los pasos 3 a 6 (no hay estado que respaldar
salvo el token, que se regenera en el portal).

## Alternativas evaluadas (octubre de 2026)

| Plataforma | Resultado |
|---|---|
| Fly.io | Sin capa gratuita para cuentas nuevas y con tarjeta obligatoria tras la prueba (7 días). Dos máquinas de 512 MB salen unos 7 a 10 USD al mes (estimación). Sus secretos son variables de entorno, lo que debilita la protección del token |
| Koyeb | Sin plan gratuito confirmado. Aunque exista una instancia gratis, es un solo servicio web que se apaga sin tráfico HTTP y no puede ser *worker*: un bot de Discord se dormiría |

En cualquiera de las tres, YouTube puede bloquear la IP del datacenter (paso 7).

## Si algo se filtra

| Qué | Qué hacer, en este orden |
|---|---|
| **Token de Discord** | Portal → Bot → *Reset Token*. Después `FORCE=1 deploy/create-secrets.sh` y `docker compose up -d` |
| **Clave del resolver** | `FORCE=1 deploy/create-secrets.sh` y `docker compose up -d --force-recreate` |
| **Cookies de YouTube** | Cerrá sesión y cambiá la contraseña de esa cuenta descartable; generá cookies nuevas |
| **Acceso a la VM** | Terminá la instancia, creá otra desde cero y rotá todo lo anterior |
| **Token de GitHub** | `gh auth logout` y revocalo en la configuración de GitHub |

## Checklist de la cuenta (lo que el código no puede hacer por vos)

- [ ] MFA en Oracle, GitHub, Discord y la cuenta de Google descartable
- [ ] Cuenta de Oracle sin *Pay as you go* y con alerta de presupuesto
- [ ] Lista de seguridad con SSH solo desde tu IP
- [ ] *Public Bot* desactivado y `DISCORD_GUILD_ID` definido
- [ ] En GitHub: *Secret scanning* y *Push protection* activados (Settings → Code security)
- [ ] La clave SSH privada solo en tu PC

## Límites conocidos

- La protección contra Slowloris está en la aplicación (plazo de headers y tope de conexiones por IP),
  no en un proxy inverso. Alcanza porque el resolver no está expuesto.
- La actualización automática de `yt-dlp` instala desde PyPI en tiempo de ejecución. Es una decisión
  consciente: es la pieza que más se rompe y ya es la que ejecutamos. Se puede desactivar con
  `YTDLP_AUTO_UPDATE=false` y actualizar reconstruyendo la imagen.
- No se usan dependencias con *hashes* fijos (`--require-hashes`): se compensa con versiones exactas,
  `pip-audit` en CI y Dependabot.
- Docker Desktop (donde se probó) no refleja los permisos de archivo reales de Linux: en la VM, los
  secretos deben ser propiedad del uid 10001, cosa que `create-secrets.sh` hace.
