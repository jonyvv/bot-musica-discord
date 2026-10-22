# Puesta en marcha

## 1. Requisitos en tu PC (Windows)

| Herramienta | Para qué | Instalación |
|---|---|---|
| Python 3.11 o superior | Ejecutar los servicios | python.org |
| **FFmpeg** | Convertir el audio. **Sin esto el bot se conecta pero no suena** | `winget install Gyan.FFmpeg` y abrir una terminal nueva |
| Node 20+ (o Deno) | Lo necesita `yt-dlp` para resolver los desafíos de YouTube | nodejs.org |

El bot comprueba FFmpeg al arrancar y se detiene con un mensaje si no lo encuentra.

## 2. Crear la aplicación de Discord

Hacelo desde una cuenta que no te duela perder (ver [04-seguridad.md](04-seguridad.md)).

1. Entrá a <https://discord.com/developers/applications> → **New Application**.
2. Pestaña **Bot** → **Reset Token** → copiá el token. Se muestra una sola vez.
3. En esa misma pestaña **desactivá *Public Bot*** (así nadie más puede invitarlo) y **no actives
   ningún *Privileged Gateway Intent***: el bot usa solo comandos slash y no lee mensajes.
4. Copiá el **Application ID** (pestaña *General Information*).
5. Invitá el bot a tu servidor con este link, reemplazando `APP_ID`:

```
https://discord.com/oauth2/authorize?client_id=APP_ID&scope=bot%20applications.commands&permissions=3164160
```

Esos permisos son solo: conectar, hablar, enviar mensajes e insertar enlaces. **Nunca** `Administrator`:
si el token se filtrara, el daño queda limitado a lo que el bot puede hacer.

6. Activá el *Modo desarrollador* en Discord (Ajustes → Avanzado), clic derecho en tu servidor →
   **Copiar ID**. Ese número es `DISCORD_GUILD_ID`: los comandos aparecen al instante y el bot **solo
   opera en ese servidor**.

## 3. Correr en local

```powershell
.\scripts\dev.ps1 setup      # entorno virtual, dependencias y .env (sin secretos)
.\scripts\dev.ps1 token      # pide el token SIN mostrarlo y lo guarda cifrado en Windows
.\scripts\dev.ps1 keygen     # genera la clave bot -> resolver (cifrada) y guarda su hash en .env
```

Editá `.env` y completá solo `DISCORD_GUILD_ID`. **El token no va en `.env`**: queda en el
Administrador de credenciales de Windows. Después, en dos terminales:

```powershell
.\scripts\dev.ps1 resolver
.\scripts\dev.ps1 bot
```

Probalo: entrá a un canal de voz y escribí `/play` con un link de YouTube, uno de Spotify o el
nombre de una canción. Mientras lo usás, la PC no puede suspenderse: se cortaría la voz.

Para comprobar que el audio realmente se puede decodificar (sin necesitar Discord):

```powershell
$env:PYTHONPATH = "services/bot/src;scripts"
.\.venv\Scripts\python.exe scripts\smoke_playback.py "https://open.spotify.com/playlist/TU_ID" --limit 5
```

## 4. Correr con Docker

Para una prueba local o para la nube. Para un servidor real, seguí
[05-despliegue-nube.md](05-despliegue-nube.md), que incluye el endurecimiento del host.

```bash
deploy/create-secrets.sh                 # clave del resolver + token (pedido sin eco) -> ./secrets/
echo "DISCORD_GUILD_ID=ID_DE_TU_SERVIDOR" > .env
mkdir -p data/cookies && sudo chown 10001 data/cookies
docker compose up -d --build
scripts/audit_containers.sh              # verifica el endurecimiento
```

- Los secretos son **archivos** montados en `/run/secrets` (no variables de entorno) y cada servicio
  ve solo los suyos.
- El resolver **no publica ningún puerto**; solo el bot lo alcanza, y con clave.
- El `chown 10001` es necesario: los contenedores corren como un usuario sin privilegios (uid 10001) y
  `yt-dlp` reescribe las cookies al refrescarlas.
- Con `YTDLP_AUTO_UPDATE=true` (por defecto en el compose) el resolver busca una versión nueva de
  `yt-dlp` al arrancar y cada 24 h, y se reinicia solo con ella.

## 5. Cookies de YouTube (solo si hace falta)

En tu PC normalmente no hacen falta. Desde un servidor en la nube, YouTube suele responder *"Sign in to
confirm you're not a bot"*; en ese caso el bot lo avisa como `bot_detected`.

1. Creá una **cuenta de Google descartable**. Nunca uses la personal: las cookies equivalen a una
   sesión iniciada de Google, y `yt-dlp` puede hacer que YouTube sancione la cuenta.
2. En una **ventana privada**, iniciá sesión en YouTube y exportá las cookies con una extensión de
   "cookies.txt".
3. **Cerrá la ventana sin cerrar sesión**: cerrar sesión invalida las cookies exportadas.
4. Guardá el archivo como `data/cookies/cookies.txt` (Docker) o apuntá `YOUTUBE_COOKIES_FILE` a él.
5. No uses las mismas cookies desde dos IPs a la vez (tu PC y el servidor): es una señal de abuso.

Las cookies caducan; renovarlas es mantenimiento periódico.

## 6. Tus playlists de Spotify

El bot lee las playlists desde sus páginas públicas, sin credenciales. Eso implica:

1. **La playlist tiene que ser pública.** En Spotify: clic en `⋯` sobre la playlist → **Hacer pública**.
   Después copiá el link con *Compartir → Copiar enlace a la playlist* y usalo en `/play`. Una
   playlist privada responde "No encontré ese contenido en Spotify".
2. **Se leen como máximo las primeras 100 canciones.** Si tu playlist es más larga, faltan las
   últimas y el bot lo avisa ("Puede estar incompleta"). Una solución simple es dividirla.
3. **"Canciones que te gustan" no se puede usar**: Spotify no la deja compartir por link. Copiá esas
   canciones a una playlist normal.

Si necesitás playlists privadas o de más de 100 canciones, hace falta leerlas con la API de Spotify
iniciando sesión con tu cuenta. Spotify exige Premium al dueño de la app y habría que guardar un token
de tu cuenta.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| El bot entra al canal pero no suena | FFmpeg no está en el `PATH` |
| `davey is not installed, voice will NOT be supported` | Falta `davey` en `services/bot/requirements.txt` (un test lo vigila) |
| Los comandos no aparecen | Falta `DISCORD_GUILD_ID`, o el bot se invitó sin `applications.commands` |
| "Este bot no está habilitado en este servidor" | El servidor no está en `DISCORD_GUILD_ID` / `ALLOWED_GUILD_IDS` |
| "No puedo comunicarme con el servicio de música" | El resolver no está corriendo |
| "El servicio de música rechazó las credenciales" | La clave del bot no coincide con la del resolver: repetí `keygen` |
| "YouTube bloqueó la consulta…" | Detección anti-bot: cookies de una cuenta descartable |
| Una canción falla con 403 en FFmpeg | `YTDLP_PLAYER_CLIENT` debe ser `tv_simply,web_embedded`; probalo con `smoke_playback.py` |
| El bot arranca y se cierra | Falta el token (`dev.ps1 token`) o `DISCORD_GUILD_ID`; el mensaje indica cuál |
| Un video no suena | Privado, restringido, dura más de 3 h o es una transmisión en vivo |
