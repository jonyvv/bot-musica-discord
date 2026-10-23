# Arquitectura

## Visión general

Dos servicios independientes que se comunican por HTTP. Cada uno está organizado en capas
con la regla de dependencia hacia adentro.

```
┌────────────────────────── bot ──────────────────────────┐        ┌──────── resolver ────────┐
│ presentation   comandos slash, embeds, validaciones     │        │ presentation  API FastAPI │
│ infrastructure voz (discord.py+FFmpeg), cliente HTTP ───┼─ HTTP ─┼─► application  clasifica, │
│ application    sesión por servidor, timers, inactividad │        │               empareja    │
│ domain         cola, modelos, errores                   │        │ infrastructure yt-dlp,    │
└─────────────────────────────────────────────────────────┘        │               Spotify     │
                                                                   │ domain        modelos     │
                                                                   └───────────────────────────┘
```

**Por qué dos servicios.** `yt-dlp` es la pieza que más se rompe (YouTube cambia su
detección seguido) y necesita actualizarse sin tocar el bot. Además concentra las cookies de
YouTube, que son el dato más sensible del proyecto: el bot nunca las ve y el resolver nunca
ve el token de Discord (ver [04-seguridad.md](04-seguridad.md)).

**Por qué no más.** La voz de Discord tiene que vivir dentro del proceso del bot (mantiene
un WebSocket y un socket UDP), así que partirlo más no aportaría nada.

## Regla de dependencia

`domain ← application ← infrastructure ← presentation`. Una capa solo importa de las que
están a su izquierda. `tests/test_architecture.py` lo verifica leyendo los imports de cada
archivo, y falla el build si alguien lo rompe. Lo mismo con el límite de 500 líneas.

Las dependencias externas entran por **puertos** (`Protocol`) definidos en `application`:
`TrackResolver`, `VoiceGateway`, `Notifier`, `ActivityObserver`. Por eso el núcleo del bot se
prueba entero sin Discord ni red.

## Contrato entre servicios

| Endpoint | Entrada | Salida |
|---|---|---|
| `POST /v1/resolve` | `{"query": "..."}` | `{kind, title, tracks[], truncated}` |
| `POST /v1/stream` | una canción | `{url, headers, expires_at, webpage_url}` |
| `GET /health` | — | `{"status": "ok"}` |

Los errores devuelven `{"code", "message"}` con códigos estables:

| Código | HTTP | Significa |
|---|---|---|
| `unsupported_input` | 422 | Link no compatible |
| `not_found` / `unavailable` / `spotify_unavailable` | 404 | No existe, es privado o está restringido |
| `bot_detected` | 503 | YouTube pidió verificación anti-bot (se registra aparte en el log) |
| `upstream_error` | 502 | Falla del proveedor; el detalle va solo al log |

`tests/test_service_contract.py` conecta el cliente real del bot con la API real del
resolver en memoria, para detectar si los dos se desincronizan.

## Flujos principales

**`/play`** — el bot valida (usuario en voz, permisos, mismo canal) → `defer` → el resolver
devuelve **solo metadatos** → se conecta al canal → encola → si estaba inactivo, pide el
stream de la primera y la reproduce.

**El audio se resuelve recién al reproducir**, no al encolar. Las URLs de YouTube vencen a
las ~6 h y resolver 500 canciones juntas sería lento. Las canciones de Spotify se buscan en
YouTube en ese momento. Entre los 5 primeros resultados se descartan los que difieren más de
15 s de la duración de Spotify y se prefiere, en este orden: sin marcas de versión alternativa
(remix, cover, parodia, instrumental, en vivo…), subido por el canal del artista pedido, y el
mejor posicionado en la búsqueda (diferencias de duración de hasta 5 s se consideran iguales).

**Fin de canción** — discord.py avisa desde el hilo de audio; el adaptador devuelve el aviso
al event loop y la sesión avanza la cola.

## Concurrencia (`application/session.py`)

- Un `asyncio.Lock` por servidor serializa `enqueue`, `skip`, `stop` y el avance de la cola.
- Un **contador de generación** invalida los avisos de reproducciones viejas: cuando se hace
  `skip` o `stop`, el callback de la canción cortada llega tarde y se descarta en vez de
  avanzar la cola por segunda vez.
- `skip` y `stop` avanzan de forma determinista, sin esperar al callback.
- Una canción que falla se avisa y se omite; bajo repetición de canción también, para no
  quedar en bucle infinito.

## Desconexión automática (`application/inactivity.py`)

Tres plazos independientes en un `TimerRegistry`. Se cancelan apenas cambia la condición que
los disparó, y cerrar la sesión cancela todos (sin temporizadores huérfanos). La función de
espera se inyecta, así que los tests avanzan un reloj manual en vez de esperar.

## Configuración

Todo por variables de entorno (ver `.env.example`).

| Variable | Servicio | Default | |
|---|---|---|---|
| `DISCORD_TOKEN` | bot | — | Obligatoria. `SecretStr`; se lee del Administrador de credenciales (local) o de `/run/secrets/discord_token` (Docker), no del `.env` |
| `DISCORD_GUILD_ID` / `ALLOWED_GUILD_IDS` | bot | — | El primero registra los comandos al instante; ambos definen dónde opera el bot, que se retira del resto |
| `IDLE_TIMEOUT` / `PAUSE_TIMEOUT` / `EMPTY_TIMEOUT` | bot | 300 / 600 / 120 | Segundos; 0 desactiva |
| `DEFAULT_VOLUME` / `MAX_QUEUE_SIZE` | bot | 50 / 1000 | |
| `MAX_TRACKS_PER_USER` / `MAX_INFLIGHT_REQUESTS` | bot | 200 / 3 | Tope de canciones encoladas por usuario y de resoluciones simultáneas |
| `RESOLVER_URL` | bot | `http://127.0.0.1:8080` | |
| `RESOLVER_API_KEY` | bot | — | Clave hacia el resolver (`SecretStr`, también desde `/run/secrets/resolver_api_key`) |
| `RESOLVER_API_KEY_SHA256` | resolver | — | Solo el hash de la clave; la comparación es en tiempo constante |
| `MAX_PLAYLIST_SIZE` / `MAX_TRACK_SECONDS` | resolver | 500 / 10800 | Lo que supera el límite de duración o es una transmisión en vivo se rechaza |
| `YTDLP_JS_RUNTIME` | resolver | `deno` | `node` en local |
| `YTDLP_PLAYER_CLIENT` / `YTDLP_FORCE_IPV4` | resolver | `tv_simply,web_embedded` / `true` | Clientes de YouTube probados en orden; cada URL se verifica como lo haría FFmpeg |
| `YOUTUBE_COOKIES_FILE` | resolver | — | Se ignora (con aviso) si el archivo no existe |
| `YTDLP_AUTO_UPDATE` / `YTDLP_UPDATE_INTERVAL_HOURS` | resolver | `false` / 24 | En Docker: se reinicia al salir una versión nueva |
| `YTDLP_MAX_CONCURRENT` / `YTDLP_MIN_INTERVAL_SECONDS` | resolver | 3 / 0,3 | Espaciado de consultas a YouTube |
| `YOUTUBE_BLOCK_THRESHOLD` / `YOUTUBE_BLOCK_COOLDOWN_SECONDS` | resolver | 3 / 600 | Cortacircuito ante detección de bot |
| `CACHE_TTL_SECONDS` | resolver | 600 | Caché con consulta única |
| `RATE_LIMIT_PER_MINUTE` / `MAX_CLIENT_CONCURRENCY` | resolver | 120 / 16 | Por cliente; 0 desactiva |
| `MAX_BODY_BYTES` / `BODY_TIMEOUT_SECONDS` | resolver | 65536 / 10 | |
| `HEADER_TIMEOUT_SECONDS` / `MAX_CONNECTIONS_PER_CLIENT` | resolver | 10 / 32 | Defensa contra Slowloris |
| `AUTH_FAILURE_LIMIT` / `AUTH_FAILURE_WINDOW_SECONDS` | resolver | 5 / 300 | Bloqueo por claves inválidas |

### Módulos de seguridad

| Módulo | Qué hace |
|---|---|
| `bot/infrastructure/secret_store.py` | Lee el token del Administrador de credenciales de Windows |
| `bot/presentation/guards.py`, `limits.py`, `permissions.py` | Lista permitida, cooldowns por usuario y servidor, auditoría de permisos |
| `bot/domain/text.py` | Limpieza y escape de texto externo |
| `bot/infrastructure/ffmpeg.py` | Whitelist de protocolos y verificación de la URL de audio |
| `resolver/presentation/auth.py`, `security.py`, `body_limit.py`, `inflight_limit.py`, `slow_clients.py` | Autenticación, límites de tasa/cuerpo/concurrencia y defensa contra conexiones lentas |
| `resolver/infrastructure/protection.py`, `pacing.py` | Caché con consulta única, espaciado y cortacircuito |
| `resolver/infrastructure/log_redaction.py` | Elimina secretos y saltos de línea de los logs |

## Cambios respecto de los requisitos (`01-requisitos.md`)

El documento de requisitos se escribió antes de construir. Esto es lo que cambió o quedó
fuera, para que no haya que adivinarlo:

| Tema | Requisito original | Lo implementado | Por qué |
|---|---|---|---|
| Arquitectura | Un solo proceso (§8.1) | Dos microservicios | Pedido explícito, y aísla `yt-dlp` y las cookies |
| Spotify | Web API con credenciales (RF-20…26) | Páginas *embed* públicas, sin credenciales | Desde 2026 la API en modo desarrollo solo permite leer playlists propias y exige Premium al dueño de la app |
| Spotify, fallos | Resumen final de omitidas (RF-23) | Aviso por canción al reproducirla | El emparejamiento con YouTube es perezoso |
| Spotify, caché | RF-26 (P2) | No implementado | |
| Anti-bot | Proveedor de PO token | No implementado | La investigación mostró que ya no alcanza (§9.3) |
| P2 sin hacer | RF-08, 17, 40, 41, 42, 44, 49b, 56, 70 | No implementados | Escenario Stage, menú de resultados, `/move`, `/jump`, `/playnext`, pre-resolución, `/seek`, config por servidor, botones |

**Límites medidos de las páginas embed de Spotify** (octubre de 2026):

- Devuelven **como máximo 100 canciones** por lista. Tres playlists editoriales de más de 100
  devolvieron exactamente 100, y la página no incluye el total, así que no se puede saber
  cuántas faltan. Al llegar a 100 la respuesta se marca como posiblemente incompleta.
- Solo leen contenido **público**. Una playlist privada o inexistente responde HTTP 200 con
  `status: 404` *dentro* de la página (no un 404 HTTP), y así se detecta.
- "Canciones que te gustan" no se puede compartir por link, así que no es accesible.
