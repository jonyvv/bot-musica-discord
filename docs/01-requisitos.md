# Bot de música para Discord — Documento de requisitos

**Versión:** 1.0 (borrador)
**Fecha:** 2026-10-20
**Estado:** pendiente de confirmar los supuestos de la sección 2

---

## 1. Objetivo

Un bot de Discord que reproduzca audio en un canal de voz a partir de links de
YouTube y de Spotify (incluyendo playlists), con una cola de reproducción por
servidor y desconexión automática cuando queda inactivo.

### 1.1 Pedido original del usuario

1. Reproducir música en un canal de voz.
2. Aceptar links de Spotify y de YouTube.
3. Soportar playlists.
4. Tener cola de reproducción.
5. Desconectarse del canal solo, si pasa mucho tiempo sin reproducir.

Los requisitos 1–5 son el núcleo obligatorio. Todo lo demás en este documento
está clasificado por prioridad (§4) para que se pueda recortar sin romper el núcleo.

---

## 2. Supuestos y decisiones (revisables)

Estos son los defaults con los que está escrito el resto del documento. Si alguno
cambia, avisame y ajusto las secciones afectadas.

| # | Decisión | Valor asumido | Por qué | Si cambia, afecta a |
|---|---|---|---|---|
| D1 | Lenguaje / librería | **Python 3.11+ con discord.py 2.x** (confirmado por el usuario) | Menos piezas que Lavalink, `yt-dlp` es una librería Python nativa (en Node hay que invocar el binario por subprocess), y una dependencia menos en una VM de 1 GB | §8, §8.4, §9, §11 |
| D2 | Motor de audio | **yt-dlp + FFmpeg**, un solo proceso | Sin JVM ni servicio aparte | §8, §6 |
| D3 | Escala | **Un solo servidor de Discord** (confirmado por el usuario) | Estado en memoria, sin base de datos, sin sharding, y **máximo 1 stream de audio simultáneo** (un bot solo puede estar en un canal de voz por servidor) | §7, §8, §9.2 |
| D4 | Persistencia | **Ninguna.** El estado vive en memoria y se pierde al reiniciar | Simplifica mucho; la cola no es un activo valioso | §7, RF-33 |
| D5 | Interfaz de comandos | **Slash commands** (`/play`), no prefijo (`!play`) | Evita el intent privilegiado *Message Content*, que Discord exige justificar | §5, §10 |
| D6 | Hosting v1 | **La PC del usuario (Windows)**, Python nativo, sin Docker | Decisión del usuario: la v1 se corre local para probar. Gratis, sin tarjeta, iteración inmediata, y la IP residencial evita el riesgo técnico #1 (§9.3) | §9.4, §6.3 |
| D6b | Hosting futuro | **Oracle Cloud Always Free, instancia ARM `A1.Flex`**, con Docker | Cuando se quiera 24/7. Costo cero estricto: una cuenta Oracle no upgradeada no puede generar cargos, y da 10 TB/mes de egreso. Google Cloud descartado porque factura el excedente (§9.2.1); Vercel, por arquitectura (§9.1.2) | §9.1, §9.2, §6.2 |
| D8 | Perfil de recursos | **v1: la PC, sin restricciones relevantes.** Futuro: 1 OCPU ARM / 6 GB, o 1/8 OCPU / 1 GB como plan B | En la v1 se usa el modo de audio de mejor calidad; el perfil reducido solo aplica al migrar | §6.3, §9.2.4, RF-49 |
| D9 | Alcance de la v1 | **Funcionalidad completa corriendo en local.** No se construye el despliegue en nube todavía | Permite empezar hoy sin depender del alta de Oracle. La contrapartida está en §9.4.3 | §9.4, §12 |
| D7 | Idioma de la interfaz | **Español** en todas las respuestas al usuario | Coherente con el uso previsto | §5 |

> **Alternativa principal descartada:** `discord.js` + **Lavalink**. Es más robusto
> para un bot público (el audio corre fuera del proceso del bot, soporta cientos de
> guilds, reconexión nativa) pero son dos servicios que mantener y requiere Java.
> Si en algún momento el bot pasa a ser público multi-servidor, migrar a Lavalink
> es el camino recomendado.

---

## 3. Alcance

### 3.1 Dentro del alcance

- Reproducción de audio en canales de voz, un canal por servidor a la vez.
- Fuentes: YouTube (video, playlist, YouTube Music), Spotify (track, álbum, playlist), búsqueda por texto.
- Cola por servidor con manipulación completa (ver, saltar, quitar, mover, mezclar, repetir).
- Controles de reproducción: pausa, reanudar, saltar, detener, volumen, seek.
- Desconexión automática por inactividad y por canal vacío.
- Mensaje de "ahora suena" con botones de control.

### 3.2 Fuera del alcance (v1)

- Descargar archivos de audio a disco para el usuario.
- Playlists guardadas / favoritos por usuario (requeriría persistencia, D4).
- Letras de canciones.
- Votación para saltar (*vote-skip*) y rol de DJ.
- Soundcloud, Apple Music, Deezer, Bandcamp, Twitch, radios por URL directa.
- Filtros de audio (bassboost, nightcore, 8D).
- Panel web o dashboard.
- Modo 24/7 (quedarse en el canal indefinidamente) — contradice el requisito 5.

Las fuentes extra (§3.2) son fáciles de agregar después: `yt-dlp` ya soporta
Soundcloud y Bandcamp, así que es cuestión de ampliar el enrutador de §8.2.

---

## 4. Prioridades

- **P0 — Obligatorio:** sin esto el bot no cumple el pedido original.
- **P1 — Importante:** se espera de cualquier bot de música; incluirlo en v1.
- **P2 — Deseable:** agregar si el tiempo lo permite.

---

## 5. Requisitos funcionales

### 5.1 Conexión al canal de voz

| ID | Prioridad | Requisito |
|---|---|---|
| RF-01 | P0 | Al invocar `/play`, si el bot no está conectado, se une al canal de voz en el que está quien ejecutó el comando. |
| RF-02 | P0 | Si quien invoca no está en ningún canal de voz, el bot responde con un error claro y no hace nada. |
| RF-03 | P0 | Antes de conectarse, el bot verifica que tiene permisos `Connect` y `Speak` en ese canal; si no, lo informa. |
| RF-04 | P1 | Si el canal tiene límite de usuarios y está lleno, el bot lo informa en vez de fallar silenciosamente (excepción: si tiene `Move Members`, Discord le permite entrar igual). |
| RF-05 | P1 | Si el bot ya está reproduciendo en otro canal del mismo servidor, los comandos de control solo los acepta de usuarios que estén en **ese** canal. |
| RF-06 | P1 | Si un administrador mueve el bot a otro canal, el bot continúa reproduciendo sin cortar el audio. |
| RF-07 | P1 | Si el bot es desconectado a la fuerza (kick del canal), limpia su estado y vacía la cola de ese servidor. |
| RF-08 | P2 | Si el canal de voz es un *Stage Channel*, el bot se solicita a sí mismo como orador (`request_to_speak`) o informa que necesita el permiso. |

### 5.2 Entrada: qué se puede pedir

| ID | Prioridad | Requisito |
|---|---|---|
| RF-10 | P0 | Acepta URL de video de YouTube (`youtube.com/watch?v=`, `youtu.be/`, `/shorts/`, `music.youtube.com`). |
| RF-11 | P0 | Acepta URL de playlist de YouTube (`?list=`) y encola todos sus elementos en orden. |
| RF-12 | P0 | Si la URL es un video **dentro** de una playlist (`watch?v=X&list=Y`), el bot pregunta —o aplica una política configurable— si encolar solo el video o toda la playlist. Default: solo el video. |
| RF-13 | P0 | Acepta URL de track de Spotify (`open.spotify.com/track/...` y `spotify:track:...`). |
| RF-14 | P0 | Acepta URL de playlist de Spotify pública y encola todos sus tracks en orden. |
| RF-15 | P1 | Acepta URL de álbum de Spotify. |
| RF-16 | P1 | Acepta texto libre como búsqueda (`/play dua lipa levitating`) y reproduce el mejor resultado. |
| RF-17 | P2 | Con texto libre, ofrece los 5 primeros resultados en un menú de selección en vez de elegir automáticamente. |
| RF-18 | P1 | Entradas no soportadas o inválidas producen un mensaje de error que dice **qué** se soporta, no un stack trace. |
| RF-19 | P1 | Las playlists se encolan con un tope configurable (`MAX_PLAYLIST_SIZE`, default **500**) para no agotar memoria ni cuota de API; si se supera, encola las primeras N y avisa. |

### 5.3 Spotify: cómo se resuelve

> **Restricción fundamental.** Spotify **no permite** obtener el audio de sus canciones
> vía API. Lo único que entrega son metadatos. Ver §6.1 para el detalle y los riesgos.

| ID | Prioridad | Requisito |
|---|---|---|
| RF-20 | P0 | Para un link de Spotify, el bot consulta la Web API de Spotify (flujo *Client Credentials*) y obtiene título, artistas, duración y, si está disponible, el ISRC de cada track. |
| RF-21 | P0 | Con esos metadatos, el bot busca el equivalente en YouTube Music / YouTube y reproduce ese resultado. |
| RF-22 | P1 | La búsqueda de equivalencia usa `"<artista> - <título>"` y descarta candidatos cuya duración difiera más de ~15 s de la de Spotify, para evitar remixes, covers, versiones extendidas y "1 hour loop". |
| RF-23 | P1 | Si no se encuentra equivalente para un track de una playlist, ese track se omite, se registra, y al final se informa cuántos quedaron fuera. Un track fallido **no** aborta la carga de la playlist. |
| RF-24 | P1 | El bot usa paginación para playlists de Spotify de más de 100 tracks (límite por página de la API). |
| RF-25 | P1 | Las playlists privadas o no accesibles con *Client Credentials* devuelven un mensaje explicando que debe ser pública. |
| RF-26 | P2 | Los metadatos de Spotify ya resueltos se cachean en memoria (TTL ~24 h) para no repetir llamadas por el mismo link. |

### 5.4 Cola de reproducción

| ID | Prioridad | Requisito |
|---|---|---|
| RF-30 | P0 | Cada servidor tiene su propia cola, independiente de los demás. |
| RF-31 | P0 | `/play` con algo ya reproduciéndose **agrega al final** de la cola en vez de interrumpir. |
| RF-32 | P0 | Al terminar una canción, la siguiente arranca automáticamente sin intervención. |
| RF-33 | P0 | Al vaciarse la cola, el bot queda conectado y en silencio, y arranca el temporizador de inactividad (RF-50). |
| RF-34 | P0 | `/queue` muestra la cola paginada (10 por página) con posición, título, duración y quién la pidió, más la duración total restante. |
| RF-35 | P1 | `/nowplaying` muestra la canción actual con una barra de progreso, duración, fuente y solicitante. |
| RF-36 | P1 | `/remove <posición>` quita un elemento puntual de la cola. |
| RF-37 | P1 | `/clear` vacía la cola sin detener la canción en curso. |
| RF-38 | P1 | `/shuffle` mezcla los elementos pendientes (no afecta a la canción en curso). |
| RF-39 | P1 | `/loop <off \| track \| queue>`: sin repetición, repetir la canción actual, o reencolar cada canción al final al terminar. |
| RF-40 | P2 | `/move <desde> <hasta>` reordena un elemento. |
| RF-41 | P2 | `/jump <posición>` salta directamente a un elemento, descartando los anteriores. |
| RF-42 | P2 | `/playnext <query>` inserta en la posición 1 en vez del final. |
| RF-43 | P1 | Las URLs de stream se resuelven **justo antes de reproducir**, no al encolar. Las URLs de YouTube caducan (~6 h) y resolver 500 tracks de golpe es lento y propenso a rate limit. Al encolar solo se guardan metadatos. |
| RF-44 | P2 | El bot pre-resuelve la URL de la **siguiente** canción mientras suena la actual, para que la transición sea sin pausa audible. |

### 5.5 Controles de reproducción

| ID | Prioridad | Requisito |
|---|---|---|
| RF-45 | P0 | `/skip` corta la canción actual y pasa a la siguiente; con cola vacía, detiene la reproducción. |
| RF-46 | P1 | `/pause` y `/resume`. Mientras está pausado corre un temporizador propio (RF-52). |
| RF-47 | P1 | `/stop` detiene la reproducción, vacía la cola y deja el bot conectado (o desconecta, según `STOP_DISCONNECTS`, default `true`). |
| RF-48 | P1 | `/disconnect` (alias `/leave`) desconecta de inmediato y limpia el estado. |
| RF-49 | P1 | `/volume <0-150>` ajusta el volumen del bot en ese servidor; el valor persiste entre canciones durante la sesión. Default **50**. |
| RF-49b | P2 | `/seek <mm:ss>` salta a una posición de la canción actual (requiere reiniciar el proceso de FFmpeg con `-ss`). No disponible en streams en vivo. |

### 5.6 Desconexión automática — requisito 5 del pedido

Son **tres** temporizadores distintos, con causas distintas. Todos son configurables
y se pueden desactivar poniéndolos en `0`.

| ID | Prioridad | Requisito |
|---|---|---|
| RF-50 | P0 | **Inactividad:** si el bot está conectado, no está reproduciendo nada y la cola está vacía durante `IDLE_TIMEOUT` (default **5 min**), se desconecta y avisa en el canal de texto. |
| RF-51 | P0 | **Canal vacío:** si no queda ningún usuario humano en el canal de voz durante `EMPTY_TIMEOUT` (default **2 min**), el bot se desconecta, incluso si estaba reproduciendo. (Otros bots no cuentan como humanos.) |
| RF-52 | P1 | **Pausa prolongada:** si la reproducción queda en pausa durante `PAUSE_TIMEOUT` (default **10 min**), el bot se desconecta. |
| RF-53 | P0 | Cualquier temporizador activo se **cancela** en cuanto cambia la condición que lo disparó: entra una canción nueva, se reanuda la reproducción, o vuelve a entrar un humano al canal. No debe quedar un temporizador zombi que desconecte el bot en medio de una canción. |
| RF-54 | P0 | La desconexión automática libera todos los recursos del servidor: cierra el proceso de FFmpeg, descarta la cola, cancela tasks pendientes y borra la entrada del estado en memoria. Sin fugas de memoria ni procesos huérfanos. |
| RF-55 | P1 | Al desconectarse por inactividad, el bot manda un mensaje breve explicando el motivo ("Me desconecté por inactividad"), no se va en silencio. |
| RF-56 | P2 | Los tres timeouts son configurables **por servidor** mediante un comando de admin, no solo por variable de entorno global. (Requiere persistencia — ver D4.) |

### 5.7 Permisos y validación

| ID | Prioridad | Requisito |
|---|---|---|
| RF-60 | P0 | Todos los comandos validan que el invocador esté en un canal de voz y, si el bot ya está conectado, que sea el mismo canal (RF-05). |
| RF-61 | P1 | Los comandos destructivos (`/stop`, `/clear`, `/disconnect`) los puede usar cualquiera en el canal en v1; queda documentado como punto a endurecer si el bot se abre a más gente. |
| RF-62 | P1 | Los comandos se limitan por usuario (*cooldown* de ~2 s para `/play`, ~5 s para operaciones de playlist) para evitar abuso accidental. |
| RF-63 | P1 | Ninguna respuesta de error expone tokens, rutas internas ni trazas; esas van solo al log. |

---

## 6. Restricciones técnicas y riesgos

Esta es la sección que más suele subestimarse en este tipo de proyecto. Vale leerla
antes de empezar.

### 6.1 Spotify no se puede reproducir directamente

- La Web API de Spotify entrega **solo metadatos**. No hay forma legítima de obtener
  el audio: está cifrado y atado a los clientes oficiales de Spotify.
- El patrón universal (el que usaban Rythm, Hydra, Groovy y usan todos los bots
  actuales) es: *metadatos de Spotify → buscar en YouTube → reproducir de YouTube*.
  Eso es lo que especifica RF-20/RF-21.
- **Consecuencia práctica:** la canción que suena puede no ser exactamente la de
  Spotify. Puede ser un live, un cover, una versión con intro distinta. RF-22
  (filtro por duración + match por artista) mitiga esto pero no lo elimina.
- **Riesgo de ToS, dicho sin vueltas:** este patrón viola los términos de servicio de
  YouTube (extracción de streams fuera de su reproductor) y discutiblemente los de
  Spotify (usar sus metadatos para servir audio de otra fuente). En 2021 Google cerró
  Rythm y Groovy justamente por esto. Para un bot personal en un servidor chico el
  riesgo real es bajo; para un bot público con miles de servidores, es alto y
  concreto. No hay una variante "legal" de este requisito — si eso es inaceptable,
  el proyecto no es viable como está planteado y habría que replantearlo sobre
  fuentes con licencia explícita para bots.
- **Endpoints restringidos:** desde fines de 2024, Spotify dejó de dar acceso a
  ciertos endpoints a las aplicaciones nuevas (entre ellos *audio-features*,
  *recommendations*, *related-artists*, los previews de 30 s y las playlists
  editoriales/algorítmicas propias de Spotify, tipo *Discover Weekly* o *Top 50*).
  Los endpoints de track, álbum, búsqueda y playlists **creadas por usuarios** siguen
  disponibles. **A verificar al empezar:** si el bot debe poder cargar playlists
  oficiales de Spotify, hay que confirmar contra la documentación vigente si eso
  sigue siendo posible para una app nueva. Si no lo es, RF-14 queda limitado a
  playlists de usuario.
- Rate limit de Spotify: ventana móvil, del orden de ~180 requests/min. Con
  paginación de 100 tracks (RF-24) y caché (RF-26) no debería ser un problema.

### 6.2 YouTube es un blanco móvil

- **`yt-dlp` se rompe seguido.** YouTube cambia su extracción de firmas cada pocas
  semanas. El bot necesita una estrategia de actualización: fijar la versión en la
  imagen pero poder actualizarla rápido, y un health check que detecte el fallo.
  Un `yt-dlp` de tres meses probablemente ya no funcione.
- **Detección de bots.** Desde una IP de datacenter, YouTube responde con frecuencia
  *"Sign in to confirm you're not a bot"*. **Con un host gratuito (D6) esto pasa de ser
  un riesgo a ser casi una certeza:** los rangos de IP de los free tiers (Oracle, GCP,
  Render, Railway) están entre los más usados por scrapers del mundo y YouTube los tiene
  muy marcados. Hay que asumir que la mitigación no es opcional sino parte del trabajo
  base.
  **Esto es el riesgo técnico #1 del proyecto, por encima de cualquier otro**, y hay que
  validarlo en la instancia real **antes** de construir el bot, no después (RNF-47).
  La estrategia completa —cookies de cuenta descartable como medida principal, por qué
  los PO token ya no alcanzan, y el análisis de la opción de proxy— está en **§9.3**.
- Videos restringidos por edad, bloqueados por región, o solo para miembros no son
  reproducibles. RF-23 cubre el manejo del fallo.
- Los streams en vivo sí se pueden reproducir pero no tienen duración ni seek;
  hay que tratarlos como caso especial.
- Las URLs de stream caducan (~6 h). De ahí RF-43 (resolución tardía).

### 6.3 Discord y audio

- Discord espera **Opus a 48 kHz estéreo**. FFmpeg hace la conversión.
- FFmpeg necesita flags de reconexión para que un corte de red no mate la canción:
  `-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5`.
- `PyNaCl` es obligatorio para voz en discord.py; FFmpeg tiene que estar en el `PATH`
  del contenedor.
- **Trade-off de volumen (RF-49).** Hay tres caminos, de más a menos CPU:

  | Opción | CPU | Volumen en vivo |
  |---|---|---|
  | `FFmpegPCMAudio` + `PCMVolumeTransformer` | Alta — Python codifica Opus en cada frame de 20 ms | Sí, instantáneo |
  | `FFmpegOpusAudio` + filtro `-filter:a volume=` | Media — FFmpeg recodifica a Opus | Sí, reiniciando el stream |
  | `FFmpegOpusAudio.from_probe(...)` → `-c:a copy` | Mínima — se copia el Opus que ya trae YouTube, sin recodificar | **No, imposible** |

  La tercera es tentadora en una instancia chica porque el audio de YouTube ya viene en Opus
  y se puede pasar tal cual, pero copiar el stream hace **imposible** aplicar cualquier
  filtro, y el volumen es un filtro. No se puede tener las dos cosas.

  **Decisión: depende del perfil de instancia, y por eso es configurable** (RNF-26).
  Dado **D3** (un solo servidor ⇒ un solo stream de audio como máximo):

  - **En la v1, corriendo en tu PC (D6), se usa la opción 1**: volumen instantáneo, sin
    cortes. Hay CPU de sobra y es la mejor experiencia.
  - En el perfil futuro de Oracle (**1 OCPU ARM / 6 GB**) la opción 1 también entra, así
    que migrar no obliga a degradar nada.
  - En el plan B (**1/8 OCPU / 1 GB**, si no hay capacidad ARM) se usa la **opción 2**:
    cambiar el volumen reinicia el stream desde la posición actual, con un corte de
    audio de una fracción de segundo.

  Si incluso la opción 2 resultara pesada, el último recurso es la opción 3 y reemplazar
  `/volume` por la instrucción de usar el control de volumen por usuario que ya trae
  Discord (click derecho sobre el bot). Para un server de amigos es una pérdida menor.
- Un bot solo puede estar en **un** canal de voz por servidor. En varios servidores a
  la vez, sí.
- Cada sesión de audio consume CPU real. Con D3 esto es irrelevante; un VPS de 1 vCPU
  aguanta unas pocas sesiones simultáneas y no mucho más.
- Usar solo slash commands (D5) evita pedir el intent *Message Content*, que Discord
  exige justificar por escrito a partir de 100 servidores.

### 6.4 Concurrencia

- Dos usuarios ejecutando `/play` a la vez en el mismo servidor no deben corromper la
  cola. Hace falta un lock por servidor alrededor de las mutaciones de estado.
- El callback `after=` de discord.py corre en otro thread; para avanzar la cola hay que
  volver al event loop con `asyncio.run_coroutine_threadsafe`. Es la fuente clásica de
  bugs de "la cola se saltea canciones" o "se reproducen dos a la vez".
- Cargar una playlist de 500 tracks no debe bloquear el event loop ni los demás comandos.
  La carga va en una task de fondo que reporta progreso.

---

## 7. Estado en memoria

Una instancia de `GuildMusicState` por servidor, creada al conectarse y destruida al
desconectarse (RF-54):

| Campo | Tipo | Para qué |
|---|---|---|
| `guild_id` | int | Clave |
| `voice_client` | VoiceClient | Conexión activa |
| `queue` | deque[Track] | Pendientes |
| `current` | Track \| None | En reproducción |
| `loop_mode` | enum(off, track, queue) | RF-39 |
| `volume` | float 0.0–1.5 | RF-49 |
| `text_channel_id` | int | Dónde avisar (RF-55) |
| `idle_task` | Task \| None | RF-50 |
| `empty_task` | Task \| None | RF-51 |
| `pause_task` | Task \| None | RF-52 |
| `lock` | asyncio.Lock | §6.4 |
| `started_at` | datetime | Barra de progreso (RF-35) |
| `now_playing_message_id` | int \| None | Para editar el panel (RF-70) |

`Track` guarda: `title`, `artists`, `duration`, `webpage_url`, `thumbnail`,
`requester_id`, `source` (youtube/spotify/search), `spotify_meta` (si aplica), y
`stream_url` + `stream_expires_at`, ambos poblados tarde (RF-43).

---

## 8. Arquitectura propuesta

### 8.1 Componentes

```
Discord Gateway
      │
      ▼
  bot.py ──────────── cogs/music.py        comandos slash, validaciones
      │                     │
      │                     ├── player.py   loop de reproducción, avance de cola
      │                     ├── state.py    GuildMusicState, timeouts
      │                     └── ui.py       embeds y botones
      │
      └── sources/
            ├── router.py     clasifica la entrada → fuente
            ├── youtube.py    yt-dlp: extracción y búsqueda
            └── spotify.py    Web API: metadatos + resolución a YouTube
```

### 8.2 Flujo de `/play <input>`

1. Validar invocador y permisos (RF-01…04, RF-60).
2. `defer()` la interacción — resolver puede tardar más de los 3 s que da Discord.
3. `router.classify(input)` → `youtube_video | youtube_playlist | spotify_track | spotify_album | spotify_playlist | search`.
4. Resolver **solo metadatos** (RF-43). Para colecciones, en una task de fondo con progreso.
5. Encolar. Si nada suena, arrancar el player.
6. Cancelar el temporizador de inactividad (RF-53).
7. Responder: "Agregado a la cola" o "Agregados N tracks (M omitidos)".

### 8.3 Flujo del player

1. Tomar el siguiente track según `loop_mode`.
2. Resolver `stream_url` (reintento una vez si falla; si vuelve a fallar, omitir y avisar — RF-23).
3. `FFmpegPCMAudio` + `PCMVolumeTransformer` → `voice_client.play(..., after=callback)`.
4. Publicar / editar el panel de "ahora suena" (RF-70).
5. En el callback: volver al event loop y repetir. Si la cola quedó vacía, arrancar `idle_task` (RF-50).

### 8.4 Dependencias

Confirmado D1 (Python), el stack queda:

| Dependencia | Para qué | Notas |
|---|---|---|
| `discord.py` 2.x | Gateway, slash commands, voz | Instalar con el extra de voz (`discord.py[voice]`), que arrastra `PyNaCl` |
| `PyNaCl` | Cifrado del audio de voz | **Obligatorio** o el bot no puede transmitir. Hay wheel para arm64 |
| `yt-dlp` | Extracción de YouTube | Se actualiza seguido (§6.2). Se usa como librería, no como binario |
| **FFmpeg** | Transcodificación de audio | Binario del sistema, no un paquete de Python. Tiene que estar en el `PATH` del contenedor |
| **Deno** (o Node) | Runtime de JavaScript que `yt-dlp` necesita para resolver los desafíos de YouTube | Binario del sistema. Dependencia nueva y **obligatoria** (RNF-35): `yt-dlp` ya no se arregla solo con Python |
| `aiohttp` | Cliente HTTP asíncrono | Ya viene con discord.py; se reutiliza para la API de Spotify y el health check |
| `python-dotenv` | Carga del `.env` | Solo para desarrollo local; en la VM las variables van por Docker |

**Spotify sin SDK.** No hace falta `spotipy`: el flujo *Client Credentials* son dos
llamadas HTTP y `aiohttp` ya está disponible. `spotipy` es sincrónico, así que meterlo
en un bot `asyncio` obliga a ejecutarlo en un thread aparte — más complejidad y una
dependencia extra para nada.

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-50 | P0 | Las versiones quedan fijadas (`requirements.txt` con versiones exactas o `uv.lock`), **salvo `yt-dlp`**, que necesita poder actualizarse sin rebuildear (RNF-11, RNF-34). |
| RNF-51 | P1 | FFmpeg y el runtime de JS vienen del gestor de paquetes de la imagen base, no compilados a mano. |

---

## 9. Configuración y despliegue

Todo por variables de entorno, sin valores hardcodeados.

| Variable | Requerida | Default | Qué hace |
|---|---|---|---|
| `DISCORD_TOKEN` | sí | — | Token del bot |
| `SPOTIFY_CLIENT_ID` | sí* | — | *Obligatoria solo si se quieren links de Spotify |
| `SPOTIFY_CLIENT_SECRET` | sí* | — | ídem |
| `IDLE_TIMEOUT` | no | `300` | Segundos sin reproducir antes de desconectar (RF-50) |
| `EMPTY_TIMEOUT` | no | `120` | Segundos con el canal vacío antes de desconectar (RF-51) |
| `PAUSE_TIMEOUT` | no | `600` | Segundos en pausa antes de desconectar (RF-52) |
| `DEFAULT_VOLUME` | no | `50` | Volumen inicial (RF-49) |
| `MAX_QUEUE_SIZE` | no | `1000` | Tope de la cola por servidor |
| `MAX_PLAYLIST_SIZE` | no | `500` | Tope por playlist encolada (RF-19) |
| `STOP_DISCONNECTS` | no | `true` | Si `/stop` también desconecta (RF-47) |
| `LOG_LEVEL` | no | `INFO` | Verbosidad |

Permisos del bot al invitarlo: `Connect`, `Speak`, `Send Messages`,
`Embed Links`, `Read Message History`, `Use Slash Commands`. **Nada más** —
en particular, no hace falta `Administrator`.

### 9.1 Hosting gratuito

#### 9.1.1 Qué necesita este bot de su host

Cuatro cosas, y son no negociables:

| Necesidad | Por qué |
|---|---|
| **Proceso persistente 24/7** | El bot mantiene un WebSocket abierto al gateway de Discord; si el proceso muere o se suspende, el bot aparece offline |
| **UDP de salida** | El audio de voz de Discord viaja por RTP sobre UDP, no por HTTP |
| **Binario de FFmpeg + ~300 MB RAM** | Transcodificación de audio en tiempo real |
| **Sin tope de duración de ejecución** | Una canción dura minutos; una sesión, horas |

Cualquier plataforma que no dé las cuatro queda descartada, sin importar lo cómodo
que sea su deploy.

#### 9.1.2 Plataformas descartadas (y por qué)

| Plataforma | Veredicto | Motivo |
|---|---|---|
| **Vercel** | ❌ Imposible | Serverless: sin proceso persistente, con tope de duración por invocación y **sin UDP de salida**. Puede hostear un bot de Discord que solo responda slash commands por webhook HTTP, pero ese bot **no puede entrar a un canal de voz**. No es cuestión de plan. |
| **Netlify / Cloudflare Workers / Deno Deploy** | ❌ Imposible | Mismo motivo que Vercel. Workers además corre en un runtime aislado sin FFmpeg. |
| **Heroku** | ❌ | No tiene plan gratuito desde noviembre de 2022. |
| **Replit** | ❌ | Mantener un proceso vivo ("Always On" / Reserved VM) es de pago. |
| **Glitch** | ❌ | Dejó de hostear proyectos. |
| **Railway** | ⚠️ No gratis | Terminó su free tier; queda un crédito de prueba y después mínimo mensual. Técnicamente perfecto, pero de pago. |
| **Fly.io** | ⚠️ No gratis | Las asignaciones gratuitas ya no aplican a cuentas nuevas. Buenísimo técnicamente, pero de pago. |
| **AWS free tier** | ⚠️ Temporal | 12 meses y después se cobra. Sirve para probar, no como destino. |

#### 9.1.3 Plataformas viables, en orden de recomendación

**1. Tu propia PC o una Raspberry Pi — recomendado para empezar**

- Costo real: cero.
- **Resuelve de regalo el riesgo técnico #1** (§6.2): una IP residencial casi no
  dispara la detección de bots de YouTube. Esto no es un detalle menor; es la
  diferencia entre un bot que funciona y uno que falla la mitad de las veces.
- Contra: no es 24/7 — el bot se cae cuando apagás la máquina. Para uso con amigos
  en horarios acordados, suele alcanzar perfectamente.
- Una Raspberry Pi 4 vieja resuelve el 24/7 por un costo único, si tenés una.

**2. Oracle Cloud Always Free — ✅ OPCIÓN ELEGIDA**

- Es el único free tier *permanente* con un VPS real y suficiente potencia:
  instancias ARM Ampere A1 con varios cores y bastante RAM, más un par de micro VMs
  AMD. Es una máquina Linux completa: Docker, FFmpeg, UDP, todo.
- **10 TB/mes de egreso** y, sobre todo, **imposibilidad estructural de generar cargos**
  mientras no upgradees la cuenta. Es lo que lo hace cumplir el requisito de costo cero.
- Contra 1: pide tarjeta de crédito para validar la cuenta (no cobra, pero la pide).
- Contra 2: suele haber falta de capacidad para las instancias ARM en las regiones
  más pedidas; a veces hay que reintentar o elegir otra región.
- Contra 3: Oracle puede reclamar instancias que detecta inactivas.
- Contra 4: IP de datacenter → §6.2 aplica con fuerza. La fase 7 del plan (§12) pasa
  a ser obligatoria, no opcional.
- **El detalle completo, las dos trampas del alta y el plan B están en §9.2.**

**3. Google Cloud — `e2-micro` Always Free — ❌ DESCARTADA por el requisito de costo cero**

- Técnicamente sirve: VM Linux completa, permanente, en tres regiones de EE. UU.
- **Pero da 1 GB de egreso gratis al mes (~35 h de música) y el excedente se factura**
  sin bloqueo previo. Son centavos, pero son cargos, y el requisito es costo cero
  estricto. Comparación completa en §9.2.1.
- Contra adicional: 1 GB de RAM y 0.25 vCPU de base, bastante menos que la ARM de Oracle.

**4. Render — free tier, con salvedades serias**

- El plan gratuito aplica a *web services*, que **se suspenden tras ~15 min sin
  tráfico HTTP**. Los *background workers* (lo que realmente es este bot) son de pago.
- El workaround habitual es levantar un servidor HTTP mínimo junto al bot y pingearlo
  desde un cron externo para que no se duerma. Funciona, pero es frágil, va contra el
  espíritu del plan, y un reinicio del contenedor corta la música y vacía la cola (D4).
- Viable solo como última opción.

**5. Hosts específicos para bots de Discord (bot-hosting.net, Discloud, Square Cloud)**

- Tienen planes gratuitos o por "monedas" pensados justo para esto, y el deploy es trivial.
- Contra: poca garantía de disponibilidad, recursos muy ajustados, y sus IPs están
  especialmente castigadas por YouTube porque alojan miles de bots de música. Es
  probable que §6.2 pegue más fuerte acá que en cualquier otra opción.

#### 9.1.4 Decisión tomada

**La v1 corre en la PC del usuario** (D6, D9). La nube queda para después.

Esto permite empezar hoy, sin depender del alta de Oracle, y con la ventaja de que la IP
residencial evita por completo el riesgo técnico #1 mientras se construye la
funcionalidad. El detalle del entorno local está en **§9.4**.

**Cuando se quiera 24/7**, el destino elegido es **Oracle Cloud Always Free, instancia
ARM `A1.Flex`** (D6b): los límites concretos, las dos trampas del alta y el plan B están
en §9.2, y el análisis de por qué se descartaron Vercel y Google Cloud en §9.1.2 y
§9.2.1. Esa sección se mantiene en el documento justamente para que la migración no
haya que volver a pensarla.

El objetivo de diseño es que ese movimiento **no requiera reescribir nada**: toda la
configuración va por variables de entorno (§9) y el código no asume el sistema
operativo ni las rutas (RNF-52 y siguientes).

| ID | Prioridad | Requisito de despliegue |
|---|---|---|
| RNF-13 | P0 | El bot corre como un proceso persistente. **No** se diseña para serverless ni se asume que puede reiniciarse sin perder estado silenciosamente. |
| RNF-14 | P0 | La misma imagen de Docker corre sin cambios en Windows/x86-64 (desarrollo local) y en Linux **arm64** (la instancia objetivo de Oracle es ARM). Ver RNF-27. |
| RNF-15 | P1 | El bot funciona con **1 sesión de audio** (el máximo posible según D3) en los dos perfiles de §9.2.4, incluido el plan B de 1 GB / 1/8 OCPU. |
| RNF-16 | P1 | El contenedor se reinicia solo si el proceso muere (`restart: unless-stopped` o unidad de systemd). |
| RNF-17 | P1 | Expone un endpoint HTTP mínimo de health check, para monitoreo externo gratuito. Escucha solo en loopback: no se abre ningún puerto de entrada en el firewall (§9.2.6). |
| RNF-18 | P2 | Si el proceso muere con una cola activa, al reiniciar avisa en el canal que la sesión se cortó, en vez de quedar en silencio. |
| RNF-19 | P1 | El bot codifica el audio a **64 kbps**, no a los 128 kbps que trae discord.py por defecto. Con 10 TB de egreso ya no es una necesidad, pero ahorra CPU y ancho de banda y la diferencia es inaudible en un canal de voz (§9.2.4). |
| RNF-20 | P0 | **La cuenta de Oracle no se upgradea a *Pay as you go* en ningún momento.** Es lo que garantiza que no pueda haber cargos: una cuenta Always Free bloquea la creación de recursos de pago en vez de facturarlos. |

### 9.2 Oracle Cloud Always Free: límites concretos

#### 9.2.1 Por qué se descartó Google Cloud

Requisito del usuario: **costo cero estricto, sin excepciones.** GCP no lo garantiza.

| | Google Cloud `e2-micro` | Oracle Cloud Always Free |
|---|---|---|
| **Egreso gratis** | **1 GB/mes** (~35 h de música) | **10 TB/mes** (~347.000 h: irrelevante) |
| **Si te pasás** | **Se factura en silencio** (~USD 0,12/GB) | **No se puede pasar:** la cuenta no upgradeada bloquea la creación de recursos de pago |
| RAM | 1 GB | Hasta 24 GB (ARM) o 1 GB (AMD) |
| CPU | 0.25 vCPU de base | Hasta 4 OCPU ARM, o 1/8 OCPU (AMD) |
| Disco | 30 GB | 200 GB |

La diferencia decisiva no es la cantidad: es que en GCP el excedente **se cobra**, y en
una cuenta Oracle no upgradeada **no existe la posibilidad de cargo**. Para un requisito
de "no quiero pagar nada" eso no es un detalle, es la respuesta.

Como efecto secundario, los 10 TB de egreso eliminan por completo el techo de ~35 h/mes
que tenía la opción de GCP. Para este bot, el egreso deja de ser una restricción.

> **Honestidad sobre la tarjeta:** Oracle **también pide una tarjeta de crédito** para
> validar la cuenta al registrarse (suele hacer una autorización temporal mínima que
> se libera). Si el requisito es no dar la tarjeta en ningún lado, entonces ninguna
> nube sirve y la respuesta es tu PC — ver §9.2.5.

#### 9.2.2 Qué incluye el Always Free

| Recurso | Límite |
|---|---|
| Compute ARM | **4 OCPU + 24 GB RAM** de `VM.Standard.A1.Flex`, repartibles en hasta 4 instancias (o todo en una) |
| Compute AMD | **2 instancias** `VM.Standard.E2.1.Micro`: 1/8 OCPU y 1 GB RAM cada una |
| Almacenamiento | 200 GB de block volume en total |
| **Egreso de red** | **10 TB/mes** |
| Ingreso de red | Gratis |
| IP pública | 1 IPv4 efímera por instancia; reservadas limitadas |

**El objetivo es una instancia ARM `A1.Flex`** con 1 OCPU y 6 GB de RAM, que es de sobra
para este bot y deja margen en la cuota por si querés otra cosa después. Comparado con
la `e2-micro` de GCP es otra categoría de máquina, gratis.

#### 9.2.3 Las dos trampas de Oracle

Hay que saberlas antes de empezar, porque las dos muerden en el momento del alta.

**1. La región se elige una sola vez y es para siempre.** La *home region* de la cuenta
se fija al registrarse y no se puede cambiar después. Y las instancias ARM del free tier
**suelen estar agotadas** en las regiones más populares: el error *"Out of host capacity"*
es la queja #1 de este free tier.

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-21 | P0 | Elegir la *home region* con criterio en el alta: una región menos saturada tiene mucha más chance de tener capacidad ARM. Entre Sudamérica (`sa-saopaulo-1`, `sa-santiago-1`) y las de EE. UU., las sudamericanas dan además menor latencia. |
| RNF-22 | P1 | Si no hay capacidad ARM, el plan B es una instancia AMD `E2.1.Micro` (1 GB / 1/8 OCPU), que casi siempre está disponible. Es más débil que la `e2-micro` de GCP en CPU, así que en ese caso aplica el perfil de recursos reducido (§9.2.4). |
| RNF-23 | P1 | Documentar en `04-deploy.md` qué región y qué tipo de instancia se usó finalmente, porque condiciona la configuración de audio. |

**2. Oracle puede reclamar instancias Always Free inactivas.** La política apunta a
instancias con uso muy bajo (del orden de CPU, red y memoria por debajo del 10% durante
7 días). Un bot de música que se usa algunas tardes por semana **podría** caer en ese
criterio durante una semana tranquila.

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-24 | P1 | Asumir que la instancia puede ser reclamada y que el despliegue tiene que ser reproducible desde cero: un script o `docker compose` que la reconstruya en minutos, con el `.env` respaldado aparte. No tratar la VM como algo irremplazable. |
| RNF-25 | P2 | Opcional: una tarea liviana periódica (el propio health check de RNF-17 más algún trabajo real) que mantenga la instancia por encima del umbral de inactividad. No inventar carga artificial pesada: desperdicia recursos y es justo lo que la política busca evitar. |

#### 9.2.4 Perfil de recursos y configuración de audio

Con la instancia ARM, el presupuesto de recursos deja de apretar, y eso **mejora la
decisión de audio de §6.3**: ya se puede pagar el costo de CPU del volumen instantáneo.

| Perfil | Instancia | Modo de audio | Volumen |
|---|---|---|---|
| **A (objetivo)** | ARM `A1.Flex`, 1 OCPU / 6 GB | `FFmpegPCMAudio` + `PCMVolumeTransformer` | Instantáneo, sin cortes |
| **B (plan B)** | AMD `E2.1.Micro`, 1/8 OCPU / 1 GB | `FFmpegOpusAudio` + filtro de volumen, 64 kbps | Reinicia el stream |

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-26 | P0 | El modo de audio es configurable por variable de entorno (`AUDIO_MODE=pcm_volume \| opus_filter`), no hardcodeado. Permite desplegar en cualquiera de los dos perfiles sin tocar código, y degradar si la CPU resulta insuficiente. |
| RNF-27 | P0 | La imagen de Docker se construye para **`linux/arm64`** (la instancia objetivo es ARM), además de `amd64` para el desarrollo local en Windows. Build multi-arquitectura. |
| RNF-28 | P1 | En el perfil B, la instancia tiene **2 GB de swap** configurados: 1 GB de RAM sin swap es propenso a OOM al cargar metadatos de playlists grandes. En el perfil A (6 GB) no es necesario. |
| RNF-29 | P1 | El contenedor declara un límite de memoria, para que un pico lo mate a él y lo reinicie (RNF-16) en vez de tumbar la VM. |

**El bitrate de 64 kbps (RNF-19) se mantiene** aunque ya no haga falta por egreso: la
diferencia es inaudible en un canal de voz de Discord, ahorra CPU y ancho de banda, y
deja margen si alguna vez hay que usar un proxy medido (§9.3). Pasa de P0 a P1.

#### 9.2.5 Si no querés dar la tarjeta en ningún lado

Oracle y GCP piden tarjeta para validar la cuenta. Si eso es un no:

1. **Tu PC, cuando lo vayan a usar.** Cero costo, cero tarjeta, y **resuelve de regalo
   el riesgo técnico #1** (§9.3): con IP residencial, la detección de bots de YouTube
   casi no aparece. El precio es que no es 24/7. Para un server de amigos que escucha
   música en ratos acordados, suele alcanzar.
2. **Hosts gratuitos específicos para bots de Discord** (bot-hosting.net, Discloud,
   Square Cloud). No piden tarjeta y el deploy es trivial, pero los recursos son muy
   ajustados, la disponibilidad no está garantizada, y sus IPs están especialmente
   castigadas por YouTube porque alojan miles de bots de música. §9.3 va a pegar más
   fuerte acá que en cualquier otra opción.

> **Nota del usuario (confirmado):** no hay Raspberry Pi ni router con WireGuard
> disponibles, así que las variantes que dependían de un equipo propio encendido en casa
> —incluido el túnel que figuraba en §9.3 de la versión anterior— quedan descartadas.
> El único equipo propio disponible es la PC de desarrollo.

#### 9.2.6 Seguridad

El bot **solo hace conexiones de salida** (gateway de Discord, UDP de voz, API de
Spotify, YouTube). No recibe conexiones entrantes de nadie.

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-30 | P0 | La *security list* / NSG de la VCN **deniega todo el tráfico entrante** salvo SSH. El health check de RNF-17 escucha en `127.0.0.1`, no en la IP pública. |
| RNF-31 | P0 | Oracle Linux y Ubuntu en Oracle traen reglas de `iptables` locales además del firewall de la VCN; hay que contemplar las dos capas o el bot parece funcionar y no responde. (Para este bot no hace falta abrir nada, así que juega a favor.) |
| RNF-32 | P0 | El token de Discord y las credenciales de Spotify viven en un `.env` con permisos `600` en la VM, nunca en la imagen de Docker ni en el repositorio. El `.gitignore` incluye `.env` desde el primer commit. |
| RNF-33 | P1 | El acceso SSH es por clave, nunca por contraseña. |

### 9.3 Mitigación de la detección de bots de YouTube

El riesgo técnico #1 (§6.2). Sección verificada en **octubre de 2026** contra la wiki
oficial de `yt-dlp`, hilos de GitHub, foros y un relato de primera mano de alguien que
peleó el problema desde la nube. Fuentes en §9.3.10.

**Dos correcciones respecto de la versión anterior de este documento:**

1. Los **PO token ya no son la mitigación principal** (§9.3.2).
2. `yt-dlp` necesita hoy un **runtime de JavaScript externo**, lo que agrega una
   dependencia a la imagen (§9.3.4, §8.4).

#### 9.3.1 Cómo funciona el problema

**No existe una forma garantizada y gratuita de que YouTube no detecte un bot que corre
desde una IP de datacenter.** Lo que hay son capas de mitigación que suben la
probabilidad de funcionar, y que requieren mantenimiento. Cualquier guía que prometa un
flag mágico está desactualizada.

El chequeo de YouTube combina tres cosas, y entenderlas explica por qué una sola medida
no basta:

| Capa | Qué evalúa | Qué la mejora |
|---|---|---|
| **Red** | Reputación de la IP. Los rangos de datacenter (AWS, GCP, Azure, Oracle, cualquier VPS) reciben el trato más estricto | Solo una IP residencial. Es la capa que **no** se arregla con software |
| **Sesión** | Confianza de la sesión, vía cookies de seguimiento | Cookies de una cuenta real con historial |
| **Cliente** | Atestación: BotGuard genera un *PO token* que prueba que el pedido viene de un player genuino. Además YouTube migró al protocolo SABR | Runtime de JS, cliente de player adecuado, `yt-dlp` al día |

El dato contraintuitivo: una sesión **nueva y limpia** de `yt-dlp` es *menos* confiable
que un perfil de navegador con historial. "Limpio" juega en contra.

#### 9.3.2 Corrección: los PO token ya no alcanzan

En la versión anterior figuraban como mitigación #1 y "el camino más estable hoy".
**Ya no.** El propio proyecto `bgutil-ytdlp-pot-provider` advierte que pasar PO tokens
no evita el chequeo de bot en la mayoría de los casos, y en el hilo de `yt-dlp` donde se
sugirió usarlos para este error, un mantenedor respondió que no iba a ayudar si el
mensaje aparece en todos los clientes.

Siguen sirviendo para otra cosa —formatos que los exigen, errores 403— así que no se
descartan, pero **pasan de ser el plan a ser complementarios**.

#### 9.3.3 La estrategia: tres capas

Lo que recomiendan consistentemente las fuentes, en este orden. Las capas 1 y 2 son
gratis; la 3 rompe el requisito de costo cero.

**Capa 1 — gratis, sin cuenta. Hacer todo esto siempre.**

Es lo primero porque no cuesta nada, no arriesga ninguna cuenta, y según varias fuentes
el cambio de cliente de player resuelve el chequeo **más confiablemente que las cookies**.

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-34 | P0 | `yt-dlp` se actualiza **automáticamente a diario**, independientemente del rebuild de la imagen (RNF-11). YouTube cambia su detección seguido y una versión de un mes probablemente ya falle. Es la medida de mayor rendimiento por esfuerzo. |
| RNF-35 | P0 | La imagen incluye un **runtime de JavaScript** (Deno, o Node) y se le indica a `yt-dlp` que lo use. Sin esto no puede resolver los desafíos actuales de YouTube. |
| RNF-36 | P0 | El **cliente de player es configurable** (`--extractor-args "youtube:player_client=..."`, p. ej. `tv,web_safari`). Varias fuentes lo señalan como el fix más efectivo que no requiere cuenta. Es un blanco móvil: el conjunto de clientes que funcionan sin token se achica, así que tiene que ser un parámetro, no una constante. |
| RNF-37 | P1 | **Forzar IPv4** (`--force-ipv4`), configurable. YouTube puntúa IPv6 con más dureza, y las VMs de nube suelen tener IPv6 habilitado. |
| RNF-38 | P1 | **Ritmo de pedidos modesto.** La wiki de `yt-dlp` lo pide explícitamente. Para este bot sale casi gratis: son unos pocos pedidos por canción, no scraping. Concretamente: no paralelizar la resolución de una playlist entera (RF-43 ya lo evita), y al pre-resolver la siguiente canción (RF-44) hacerlo de a una. |

**Capa 2 — gratis, con una cuenta descartable.**

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-39 | P0 | Las cookies provienen de una **cuenta de Google descartable**, creada para esto. La wiki oficial de `yt-dlp` advierte que usar tu cuenta con la herramienta implica **riesgo de baneo temporal o permanente**. Nunca la cuenta personal — y menos considerando que una cookie de sesión da acceso mucho más allá de YouTube. |
| RNF-40 | P0 | Las cookies se exportan desde una **ventana privada/incógnito**, y esa ventana se cierra **sin hacer logout**. Cerrar sesión invalida las cookies exportadas: es el error más común al hacer esto. |
| RNF-41 | P0 | El archivo de cookies vive en un **volumen con permisos de escritura**, nunca dentro de la imagen. `yt-dlp` reescribe las cookies al refrescarlas; si el archivo es de solo lectura, dejan de servir a los pocos días. |
| RNF-42 | P1 | Las mismas cookies **no se usan desde dos IPs a la vez** (tu PC y la VM en paralelo). Es una señal fuerte de abuso. Si se desarrolla en local y se despliega en la VM, se usan cuentas distintas. |
| RNF-43 | P1 | Las cookies caducan: `04-deploy.md` documenta el procedimiento de renovación, y el bot avisa cuando empiezan a fallar (RNF-45). Es mantenimiento periódico, no un setup de una vez. |

**Capa 3 — de pago. Descartada por el requisito de costo cero.**

El proxy residencial. Funciona —es lo único que funcionó en el test de primera mano
citado en §9.3.7— pero se factura por GB. Análisis en §9.3.6.

#### 9.3.4 Observabilidad: no quedarse a ciegas

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-44 | P0 | Toda la configuración de mitigación va por variables de entorno (`YTDLP_PLAYER_CLIENT`, `YOUTUBE_COOKIES_FILE`, `YTDLP_FORCE_IPV4`, `YOUTUBE_PO_TOKEN`, `PROXY_URL`), para cambiar de estrategia sin tocar código ni rebuildear. Dado que esto es un blanco móvil, es un requisito central, no una comodidad. |
| RNF-45 | P0 | El bot **distingue el fallo por detección de bots** de un fallo genérico de reproducción, y lo reporta como tal en el log y en el canal. Sin esto, diagnosticar en producción es imposible: todo se ve como "no se pudo reproducir". |

#### 9.3.5 Lo que NO funciona (probado por otros)

Vale documentarlo para no perder tiempo. En el relato de primera mano de alguien que
intentó esto desde un servidor en la nube, fallaron: `yt-dlp` con cookies a secas, la API
pública de Cobalt (ahora exige CAPTCHA de Cloudflare), Cobalt autohospedado, los
descargadores de RapidAPI, las herramientas web tipo SaveFrom, y la API oficial de
YouTube Data (que no tiene endpoint de descarga). Lo único que le funcionó fue el proxy
residencial.

#### 9.3.6 Sobre la idea del proxy

La intuición de "oculto la IP del servidor con un proxy" acierta en el diagnóstico. Dos
cosas la limitan:

> **Un proxy solo ayuda si es residencial.** Un proxy de datacenter o un VPN gratuito
> cambia una IP marcada por otra probablemente *más* marcada: son justo las que miles de
> scrapers ya quemaron. Un proxy barato no es una mitigación parcial, puede ser un
> empeoramiento.

**Cuánto costaría, con números reales.** Los proxies residenciales se facturan por GB,
del orden de **USD 3,50 a 6 por GB** según plan. Con la optimización de formato de
§9.3.9 el bot baja ~31 MB por hora de música, así que:

| Uso mensual | Tráfico | Costo estimado |
|---|---|---|
| 35 h | ~1,1 GB | ~USD 4 a 7 |
| 100 h | ~3,1 GB | ~USD 11 a 19 |

O sea: no es ruinoso en términos absolutos, pero **es un costo recurrente, y el
requisito es costo cero.** Queda descartado. Se documenta el número para que la decisión
sea informada si alguna vez cambia el criterio.

Una aclaración técnica, porque es la salida que uno intentaría: **no se puede proxear
solo la extracción y bajar el audio directo.** `yt-dlp` hace pedidos de extracción
(chicos, donde pega la detección) y la descarga del stream (grande). Sería ideal proxear
solo los primeros, pero **YouTube ata la URL del stream a la IP que la solicitó**, así
que usarla desde otra IP falla. Por el mismo motivo, si alguna vez se usa un proxy, hay
que usar **siempre el mismo**, nunca rotarlo por pedido.

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-46 | P1 | Si alguna vez se usa un proxy, se aplica **solo a `yt-dlp`**, nunca al tráfico de Discord: meter el audio de voz por un proxy agrega jitter y produce cortes. |

#### 9.3.7 Por qué este bot está en mejor posición de lo que sugieren los foros

Esto es importante para no sacar la conclusión equivocada de lo anterior. El caso donde
"solo funcionó el proxy residencial" era **un servicio público en la nube descargando
video en 1080p**: unos 400 MB por video de 17 minutos, a volumen alto y sostenido.

El perfil de este bot es radicalmente distinto:

| | Ese caso | Este bot |
|---|---|---|
| Contenido | Video 1080p | **Solo audio**, ~31 MB/hora |
| Volumen | Servicio público, alto y sostenido | Un server de amigos, ~1 h/día |
| Pedidos | Masivos | Unos pocos por canción |

Como el **ritmo de pedidos es parte de lo que YouTube puntúa** —y la wiki oficial
recomienda justamente mantenerlo modesto—, las chances de que las capas 1 y 2 alcancen
para este caso son bastante mejores que las que sugiere ese relato. **No es una
garantía**, y por eso existe §9.3.8.

#### 9.3.8 Validarlo antes de construir, no después

Con la v1 corriendo en local (D9), **nada de esta sección bloquea el arranque**: en una
IP residencial el chequeo de bots casi no aparece. Pero eso no resuelve el problema, lo
**posterga y lo esconde** — ver la advertencia de §9.4.3.

Por eso la validación no va al final de la migración sino **al principio**:

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-47 | P0 | **El primer paso de la migración a la nube, antes de portar nada**, es levantar la instancia y verificar a mano que `yt-dlp` puede extraer y descargar audio desde esa IP, aplicando la capa 1 y, si hace falta, la capa 2. Es una prueba de media hora que valida —o invalida— toda la decisión de hosting antes de invertir trabajo en portarla. |
| RNF-48 | P1 | La verificación se repite con el bot ya desplegado: funcionar a mano y funcionar dentro del contenedor no es lo mismo. |

#### 9.3.9 Si nada de esto alcanza

Hay que contemplarlo. En orden de preferencia:

1. **Correr el bot en tu PC cuando lo vayan a usar.** Gratis, no necesita nada que no
   tengas, y la IP residencial hace desaparecer el problema de raíz. El precio es que no
   es 24/7. Para un server de amigos que escucha música en ratos acordados es una
   solución real, no un parche.
2. **Cambiar el peso de las fuentes.** El problema es específico de YouTube. `yt-dlp`
   soporta SoundCloud y Bandcamp sin esta pelea. Buscar primero en SoundCloud y usar
   YouTube como respaldo reduce la dependencia de la parte frágil. No es equivalente
   —el catálogo de SoundCloud es bastante peor para música mainstream— pero como
   cobertura parcial sirve, y es lo que motiva dejar el enrutador de fuentes extensible
   (§8.2).
3. **Aceptar el costo de un proxy residencial** (§9.3.6), que es renunciar al requisito
   de costo cero.

#### 9.3.10 Optimización relacionada: bajar el formato que se descarga

YouTube ofrece el audio Opus en varias calidades (~50, ~70 y ~130 kbps) y `yt-dlp` elige
la mejor por defecto. Como el bot **recodifica a 64 kbps de salida** (RNF-19), bajar la
de ~130 kbps es trabajo y tráfico tirados.

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-49 | P1 | `yt-dlp` prefiere un formato de audio de ~70 kbps en vez del mejor disponible (`bestaudio[abr<=80]/bestaudio`), con fallback al mejor. Acelera el arranque de cada canción (RNF-01) y reduce el tráfico de descarga a la mitad (~31 MB/h en vez de ~58). |

#### 9.3.11 Riesgo adicional: la cuenta de desarrollador de Discord

Un dato que no estaba en §6.1: además del riesgo del lado de YouTube, hay proyectos que
advierten sobre el lado de **Discord** — rechazo si alguna vez se pide la verificación de
la app, y en el peor caso sanción de la cuenta de desarrollador.

Para este proyecto el riesgo es bajo: la verificación recién importa a partir de ~100
servidores y este bot va a estar en uno (D3). Pero si querés ser prolijo, **creá la
aplicación de Discord desde una cuenta que no te duela perder**.

#### 9.3.12 Fuentes consultadas

Verificado en octubre de 2026. Este tema cambia rápido: conviene revalidar en la fase 0a.

**Oficiales / primarias:**

- [yt-dlp Wiki — Extractors](https://github.com/yt-dlp/yt-dlp/wiki/extractors) — advertencia oficial de riesgo de baneo al usar una cuenta propia, recomendación de cuenta descartable y ritmo modesto de pedidos.
- [yt-dlp — issue #15865](https://github.com/yt-dlp/yt-dlp/issues/15865) — hilo donde los mantenedores desaconsejan el PO token para este error y recomiendan cookies o cambiar de IP.
- [bgutil-ytdlp-pot-provider (PyPI)](https://pypi.org/project/bgutil-ytdlp-pot-provider) — advertencia de que los PO token ya no evitan el chequeo de bot en la mayoría de los casos.

**Relato de primera mano:**

- [I Was Building a Cloud Video Service. YouTube Turned Me Into an IP Trafficker](https://dev.to/osovsky/i-was-building-a-cloud-video-service-youtube-turned-me-into-an-ip-trafficker-1l9o) — prueba de 7 métodos desde la nube, con precios de proxy residencial. Ver el contraste de perfil en §9.3.7.

**Proyectos de bots:**

- [JonPark0/MusicBot](https://github.com/JonPark0/MusicBot) — confirma el bloqueo de IPs de VPS, el atado del stream a la IP solicitante, y las cookies de cuenta secundaria.
- [blanco-bot (Docker Hub)](https://hub.docker.com/r/jareddantis/blanco-bot) — riesgo para la cuenta de desarrollador de Discord.
- [Lavalink en VPS, guía 2026](https://space-node.net/blog/discord-bot-lavalink-music-guide-2026) — las mismas restricciones en el stack Node/Lavalink.

**Guías (secundarias, contrastadas entre sí):**

- [Fix "Sign in to confirm you're not a bot"](https://yt-dlp.net/errors/sign-in-to-confirm-not-a-bot) y [Fix "PO Token required"](https://yt-dlp.net/errors/po-token-required) — orden de fixes y clientes que aún funcionan.
- [yt-dlp cookies: export, use, and when they stop working](https://tunelio.dev/blog/yt-dlp-cookies/) y [yt-dlp errors explained](https://tunelio.dev/blog/yt-dlp-errors/) — detalles de exportación de cookies y por qué dejan de funcionar.
- [yt-dlp, PO Tokens, and SABR](https://www.bigiron.cc/guides/yt-dlp-po-tokens-and-sabr-why-downloads-keep-breaking) — contexto sobre SABR.
- [Why datacenter IPs get scrutinized](https://vidkraken.com/blog/yt-dlp-sign-in-to-confirm-not-a-bot) — reputación de rangos de nube.

---

### 9.4 Entorno local (v1)

La v1 corre en la PC del usuario, Windows, con Python nativo (D6, D9).

#### 9.4.1 Sin Docker en local

Para la v1 se usa un **virtualenv**, no Docker. Docker Desktop en Windows necesita WSL2 y
agrega una capa pesada entre el código y el ciclo de prueba; para iterar sobre un bot que
se reinicia cada dos minutos, molesta más de lo que ayuda. El `Dockerfile` se escribe
recién en la fase 9, cuando haga falta.

Lo que **sí** se respeta desde el primer commit son las condiciones que hacen que esa
migración después sea barata:

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-52 | P0 | Ninguna ruta absoluta ni específica de Windows en el código. Rutas con `pathlib`, relativas o desde variables de entorno. |
| RNF-53 | P0 | Toda la configuración por variables de entorno (§9), incluso la que en local tendría un valor obvio. Es lo que permite que migrar sea cambiar un `.env`. |
| RNF-54 | P1 | Nada de dependencias exclusivas de Windows. El código tiene que poder correr en Linux sin cambios, aunque todavía no se pruebe ahí. |
| RNF-55 | P1 | FFmpeg y el runtime de JS se invocan por nombre desde el `PATH`, nunca por ruta absoluta. |

#### 9.4.2 Particularidades de Windows

| ID | Prioridad | Requisito |
|---|---|---|
| RNF-56 | P0 | **FFmpeg y Deno se instalan aparte** y tienen que quedar en el `PATH` (por ejemplo con `winget`). No vienen con Python y son la causa más común de que el bot arranque pero no suene nada. |
| RNF-57 | P0 | **Cuidado con el event loop de `asyncio` en Windows.** El default de Python 3.8+ es `ProactorEventLoop`, que es el que soporta subprocesos. `SelectorEventLoop` **no soporta subprocesos en Windows**, así que si alguna librería lo fuerza, FFmpeg deja de funcionar y el síntoma es confuso. No cambiar la política de event loop. |
| RNF-58 | P1 | La PC no puede suspenderse mientras el bot esté en uso, o se corta la conexión de voz. Queda documentado en `03-setup.md`. |
| RNF-59 | P2 | Un script de arranque (`.ps1` o `.bat`) que active el venv y levante el bot, para no depender de recordar los pasos. |

#### 9.4.3 La contrapartida: el problema de YouTube queda escondido

Hay que decirlo explícitamente, porque es el único costo real de esta decisión:

> **En local, con IP residencial, la detección de bots de YouTube casi no aparece.** Eso
> es cómodo para construir, pero significa que la v1 va a funcionar perfecto **sin
> demostrar nada** sobre si va a funcionar en la nube. El riesgo técnico #1 no se
> resuelve: se posterga.

Es un trade-off razonable —permite tener un bot andando ya, en vez de pelear con el
problema más difícil primero— pero queda registrado para que la fase 8 no sea una
sorpresa. Dos consecuencias prácticas:

1. **La fase 8 es un spike y va antes que la 9** (§12): se valida la IP de Oracle antes de
   portar nada.
2. **Las medidas de la capa 1 de §9.3.3 se implementan igual en la v1** (`yt-dlp` al día,
   runtime de JS, cliente de player configurable). No cuestan nada en local y son
   exactamente lo que la fase 8 va a necesitar.

---

## 10. Requisitos no funcionales

## 10. Requisitos no funcionales

## 10. Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-01 | De `/play` con una URL de track a primer audio audible: **< 3 s** en condiciones normales. |
| RNF-02 | Toda interacción responde o hace `defer()` dentro de los 3 s que exige Discord, sin excepción. |
| RNF-03 | Una playlist de 100 tracks queda completamente encolada en **< 30 s**, con feedback de progreso visible. |
| RNF-04 | Un fallo al resolver una canción nunca tira abajo el bot ni la sesión; se omite y se informa. |
| RNF-05 | El bot se recupera solo de desconexiones del gateway y de voz, y reanuda lo que estaba sonando cuando es posible. |
| RNF-06 | Sin fugas: al desconectarse, cero procesos de FFmpeg huérfanos y cero tasks pendientes (RF-54). |
| RNF-07 | Un servidor que falla no afecta la reproducción en los demás. |
| RNF-08 | Logs estructurados con `guild_id` en cada entrada; nunca el token ni secretos. |
| RNF-09 | Todos los mensajes de error son accionables y en español (D7); los técnicos van al log. |
| RNF-10 | El deploy es reproducible: `docker build` + `docker run` con el `.env`, sin pasos manuales. |
| RNF-11 | `yt-dlp` se puede actualizar sin rebuildear toda la imagen (§6.2). |
| RNF-12 | El bot arranca en < 10 s y registra los slash commands automáticamente. |

---

## 11. Criterios de aceptación

El bot se considera terminado cuando, en un servidor de prueba:

1. `/play <url de youtube>` → el bot se une y suena la canción.
2. `/play <url de playlist de youtube>` → encola todo en orden y arranca.
3. `/play <url de track de spotify>` → suena la canción correcta (no un cover ni un remix).
4. `/play <url de playlist pública de spotify>` de 50+ tracks → encola, informa omitidos, y suena.
5. `/play <texto>` → encuentra y reproduce algo razonable.
6. `/queue` paginado, `/nowplaying` con progreso correcto.
7. `/skip`, `/pause`, `/resume`, `/shuffle`, `/loop`, `/volume`, `/remove`, `/clear` funcionan.
8. Al terminar la cola, el bot se desconecta tras `IDLE_TIMEOUT` y lo avisa.
9. Si todos se van del canal, el bot se desconecta tras `EMPTY_TIMEOUT` aunque esté reproduciendo.
10. Encolar algo durante el conteo de inactividad **cancela** la desconexión (RF-53).
11. Dos usuarios haciendo `/play` simultáneamente dejan la cola consistente.
12. Una canción irreproducible se omite con aviso y la cola sigue.
13. Reiniciar el contenedor deja todo en estado limpio, sin FFmpeg zombis.

---

## 12. Plan por fases

| Fase | Contenido | Resultado |
|---|---|---|
| **0 — Setup local** | Aplicación de Discord, token, credenciales de Spotify, repo, venv, FFmpeg y Deno en el `PATH` de Windows (§9.4) | El bot se conecta y responde `/ping` |
| **1 — Audio mínimo** | `/play` con URL de YouTube, conexión a voz, un solo track | Suena una canción |
| **2 — Cola** | `GuildMusicState`, avance automático, `/queue`, `/skip`, `/nowplaying` | RF-30…34, RF-45 |
| **3 — Timeouts** | Los tres temporizadores + limpieza de recursos | Requisito 5 cumplido |
| **4 — Playlists de YouTube + búsqueda** | RF-11, RF-12, RF-16, RF-19 | Colecciones de YouTube |
| **5 — Spotify** | API de metadatos, resolución a YouTube, matching por duración | RF-20…26 |
| **6 — Pulido** | shuffle, loop, volumen, remove, clear, panel con botones, mensajes de error | RF-36…49, RF-70 |
| **7 — Endurecimiento** | Mitigación de detección de bots de YouTube, logs, estrategia de update de yt-dlp | §6.2 resuelto |

A lo que se suma, dado el hosting gratuito:

| Fase | Contenido | Resultado |
|---|---|---|
| **8 — Spike de nube** | *(cuando se quiera 24/7)* Alta de Oracle, región elegida con criterio, y la verificación manual de `yt-dlp` desde esa IP (RNF-47) | Se sabe si el hosting es viable **antes** de portar nada |
| **9 — Migración a 24/7** | Dockerfile e imagen arm64, firewall cerrado, compose con restart, health check (RNF-13…33) | El bot vive sin tu PC prendida |

La fase 3 va antes que las playlists a propósito: la limpieza de recursos es mucho más
fácil de hacer bien sobre un sistema simple, y es donde se esconden los bugs más molestos.

**Las fases 0 a 7 son la v1** y se hacen enteras en local (D9). Las fases 8 y 9 son la
migración futura y pueden encararse en cualquier momento.

**La fase 8 es un spike, no el deploy.** Está separada de la 9 a propósito: media hora de
prueba manual decide si Oracle sirve, antes de invertir el trabajo de portar el bot a un
contenedor. Si falla, el plan B (seguir en local, o §9.3.9) se conoce sin haber gastado
nada.

**La fase 7 conserva sentido aun estando en local**: mantener `yt-dlp` actualizado, el
runtime de JS y el cliente de player configurable sirven igual en tu PC, y es lo que
hace que la fase 8 no arranque de cero.

---

## 13. Preguntas abiertas

### Resueltas

- ✅ **Stack:** Python 3.11+ con discord.py 2.x (D1).
- ✅ **Alcance de la v1:** funcionalidad completa **corriendo en local** (D9). La nube queda para después.
- ✅ **Hosting futuro:** Oracle Cloud Always Free, instancia ARM `A1.Flex` (D6b, §9.2). Vercel descartado por arquitectura; Google Cloud, por el requisito de costo cero.
- ✅ **Costo:** cero estricto. La cuenta no se upgradea nunca (RNF-20).
- ✅ **Riesgo de ToS** de §6.1: aceptado por el usuario.
- ✅ **Escala:** un solo servidor de Discord, uso con amigos (D3) ⇒ un stream de audio máximo.

### Pendientes

1. **¿La tarjeta para validar la cuenta de Oracle es aceptable?** No bloquea nada ahora (la v1 es local), pero hay que resolverlo antes de la fase 8. No genera cargos y la cuenta no puede facturarte, pero hay que darla en el alta.
2. **Playlists oficiales de Spotify:** ¿necesitás cargar *Discover Weekly* / *Top 50* / playlists editoriales? Si sí, hay que verificar primero si la API lo permite para apps nuevas (§6.1). Las playlists que armen ustedes funcionan sin problema.
3. **Alcance de permisos:** ¿cualquiera puede usar `/stop` y `/clear`, o querés rol de DJ desde v1? (RF-61). Para un server de amigos, lo primero suele estar bien.
4. **Fuentes extra:** ¿agregamos Soundcloud desde el principio? Sale casi gratis porque `yt-dlp` ya lo soporta.
5. **Región de Oracle:** se elige una sola vez y no se puede cambiar (RNF-21). Conviene decidirla en la fase 8, según dónde haya capacidad ARM disponible.
