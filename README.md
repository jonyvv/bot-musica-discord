# Bot de música para Discord

Bot que reproduce música en canales de voz a partir de links de **YouTube** y **Spotify**
(canciones, álbumes y playlists), con cola de reproducción y desconexión automática por
inactividad. Pensado para un servidor de amigos y 100 % gratis de correr.

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
Discord ◄──► bot ──HTTP──► resolver ──► YouTube (yt-dlp)
              │                    └──► Spotify (páginas embed)
              └──► FFmpeg ──► audio de voz
```

- **`services/bot`**: comandos, cola, sesión por servidor y audio.
- **`services/resolver`**: convierte links/búsquedas en canciones y obtiene el audio. Está
  aparte porque `yt-dlp` hay que actualizarlo seguido y es lo que más se rompe.

## Puesta en marcha

Guía completa, incluida la creación de la app de Discord, en
[docs/03-setup.md](docs/03-setup.md). Resumen en Windows:

```powershell
.\scripts\dev.ps1 setup      # crea el entorno, instala dependencias y genera .env
# completar DISCORD_TOKEN en .env
.\scripts\dev.ps1 resolver   # terminal 1
.\scripts\dev.ps1 bot        # terminal 2
```

Con Docker: `docker compose up -d --build`.

Requisitos: Python 3.11+, **FFmpeg** en el `PATH` y Node 20+ (o Deno).

## Desarrollo

```powershell
.\scripts\dev.ps1 test    # tests
.\scripts\dev.ps1 lint    # ruff
```

Reglas del proyecto, verificadas automáticamente por `tests/test_architecture.py`:
ningún archivo supera las 500 líneas y cada capa solo depende de las internas.

## Estado y límites

- Verificado con tests (más de 230) y contra YouTube y Spotify reales. **No se probó contra
  un servidor de Discord real**: hace falta un token, así que la primera ejecución con audio
  es la prueba de integración pendiente.
- Las imágenes de Docker **no se construyeron** durante el desarrollo (no había motor de
  Docker disponible); solo se validó la sintaxis del compose.
- Las playlists de Spotify tienen que ser **públicas** y se leen hasta **100 canciones**
  (límite medido; el bot avisa si puede faltar alguna). Ver [docs/03-setup.md](docs/03-setup.md).
- Spotify no entrega audio: cada canción se busca en YouTube al reproducir, así que puede
  sonar una versión distinta. Ver [docs/01-requisitos.md](docs/01-requisitos.md), sección 6.1,
  por las implicancias de términos de servicio.
- Desde un servidor en la nube, YouTube suele pedir verificación anti-bot. En tu PC casi
  no ocurre. Ver sección 9.3 del mismo documento.

## Seguridad

Qué datos sensibles maneja el proyecto y cómo se protegen:
[docs/04-seguridad.md](docs/04-seguridad.md).
