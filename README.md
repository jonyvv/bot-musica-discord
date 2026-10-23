# Bot de música para Discord

Bot que reproduce música en canales de voz a partir de links de **YouTube** y **Spotify**
(canciones, álbumes y playlists), con cola de reproducción y desconexión automática por
inactividad. Pensado para un servidor de amigos, gratis de correr y endurecido para la nube.

## Comandos

| Comando | Qué hace |
|---|---|
| `/play <link o nombre>` | Reproduce o agrega a la cola. Acepta links de YouTube/Spotify o busca por texto |
| `/skip` · `/pause` · `/resume` · `/stop` | Controles de reproducción |
| `/queue [página]` · `/nowplaying` | Ver la cola y la canción actual con su progreso |
| `/remove <n>` · `/clear` · `/shuffle` | Editar la cola |
| `/loop <desactivada\|canción\|cola>` | Repetición |
| `/volume <0-150>` | Volumen, se mantiene entre canciones |
| `/leave` | Desconecta el bot |

El bot se desconecta solo tras **5 min sin reproducir**, **10 min en pausa** o **2 min con el
canal vacío** (aunque esté sonando). Los tres plazos son configurables; `0` desactiva cada uno.

## Arquitectura

Dos microservicios con arquitectura limpia (dominio ← aplicación ← infraestructura ←
presentación). Detalle en [docs/02-arquitectura.md](docs/02-arquitectura.md).

```
Discord ◄──► bot ──HTTP + clave──► resolver ──► YouTube (yt-dlp)
              │                         └─────► Spotify (páginas embed)
              └──► FFmpeg ──► audio de voz
```

- **`services/bot`**: comandos, cola, sesión por servidor y audio.
- **`services/resolver`**: convierte links/búsquedas en canciones y obtiene el audio. Está
  aparte porque `yt-dlp` hay que actualizarlo seguido, y porque concentra las cookies de YouTube.

## Instalarlo en tu servidor de Discord

1. En <https://discord.com/developers/applications> crea una **New Application**, y en la pestaña **Bot**
   usa **Reset Token** para copiar el token (se muestra una sola vez). Desactiva **Public Bot** y no
   actives ningún *Privileged Gateway Intent*.
2. Copia el **Application ID** (*General Information*) e invita el bot con este link, cambiando `APP_ID`:

   ```
   https://discord.com/oauth2/authorize?client_id=APP_ID&scope=bot%20applications.commands&permissions=3164160
   ```

   Esos permisos son solo conectar, hablar, enviar mensajes e insertar enlaces. Nunca des `Administrator`.
3. En Discord activa el *Modo desarrollador* (Ajustes → Avanzado), clic derecho en tu servidor →
   **Copiar ID**, y ponlo como `DISCORD_GUILD_ID` en `.env`. El bot solo opera en ese servidor.
4. Guarda el token con `.\scripts\dev.ps1 token` (queda cifrado, no va en `.env`) y arranca el bot
   como se explica abajo. Entra a un canal de voz y escribe `/play`.

## Puesta en marcha

Guía completa en [docs/03-setup.md](docs/03-setup.md). Resumen en Windows:

```powershell
.\scripts\dev.ps1 setup      # entorno, dependencias y .env (sin secretos)
.\scripts\dev.ps1 token      # guarda el token de Discord cifrado, sin mostrarlo
.\scripts\dev.ps1 keygen     # clave bot -> resolver
# completar DISCORD_GUILD_ID en .env
.\scripts\dev.ps1 resolver   # terminal 1
.\scripts\dev.ps1 bot        # terminal 2
```

Requisitos: Python 3.11+, **FFmpeg** en el `PATH` y Node 20+ (o Deno).

Para publicarlo en la nube con la configuración más segura: [docs/05-despliegue-nube.md](docs/05-despliegue-nube.md).

## Seguridad

El token **no se guarda en archivos de texto** (Administrador de credenciales en tu PC, secretos de
Docker en un servidor), el resolver no está expuesto y exige una clave, y el bot solo opera en tu
servidor. Se probó contra ataques reales sobre contenedores: robo de tokens, inundación, Slowloris,
inyección, SSRF y bloqueo de IP. Resultados y límites en [docs/04-seguridad.md](docs/04-seguridad.md).

## Desarrollo

```powershell
.\scripts\dev.ps1 test    # 530+ tests
.\scripts\dev.ps1 lint    # ruff
.\scripts\dev.ps1 audit   # vulnerabilidades en las dependencias
```

```bash
scripts/audit_containers.sh              # endurecimiento de los contenedores desplegados
scripts/attack_compose.sh                # ataques contra el resolver desplegado
python scripts/smoke_playback.py URL     # el audio realmente se decodifica
```

Reglas del proyecto, verificadas automáticamente: ningún archivo supera las 500 líneas, cada capa
solo depende de las internas, ninguna acción de CI ni imagen base queda sin fijar, y no se versiona
ningún secreto (`tests/`). CI en GitHub ejecuta todo esto además de CodeQL y Trivy.

## Estado y límites

- Verificado con tests, contra YouTube y Spotify reales, y en **Docker real** (auditoría de
  contenedores, 78 ataques de prueba y decodificación de audio real). **No se probó contra un
  servidor de Discord real**: hace falta un token, así que la primera ejecución con audio es la
  prueba de integración pendiente.
- Las playlists de Spotify tienen que ser **públicas** y se leen hasta **100 canciones** (límite
  medido; el bot avisa si puede faltar alguna). Ver [docs/03-setup.md](docs/03-setup.md).
- Spotify no entrega audio: cada canción se busca en YouTube al reproducir, así que puede
  sonar una versión distinta. Ver [docs/01-requisitos.md](docs/01-requisitos.md), sección 6.1, por
  las implicancias de términos de servicio.
- Desde una IP de nube, YouTube suele pedir verificación anti-bot. En tu PC casi no ocurre. Es el
  primer paso a verificar en el servidor ([docs/05-despliegue-nube.md](docs/05-despliegue-nube.md)).
