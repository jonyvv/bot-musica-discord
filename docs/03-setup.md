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
3. En esa misma pestaña **no actives ningún *Privileged Gateway Intent***: el bot usa solo
   comandos slash y no necesita leer mensajes.
4. Copiá el **Application ID** (pestaña *General Information*).
5. Invitá el bot a tu servidor con este link, reemplazando `APP_ID`:

```
https://discord.com/oauth2/authorize?client_id=APP_ID&scope=bot%20applications.commands&permissions=3164160
```

Esos permisos son solo: conectar, hablar, enviar mensajes e insertar enlaces. **No** hace
falta `Administrator`.

6. Opcional pero recomendado: activá *Modo desarrollador* en Discord (Ajustes → Avanzado),
   clic derecho en tu servidor → **Copiar ID**, y ese número es `DISCORD_GUILD_ID`. Con él los
   comandos aparecen al instante; sin él pueden tardar en propagarse.

## 3. Correr en local

```powershell
.\scripts\dev.ps1 setup
```

Crea el entorno virtual, instala las dependencias y genera `.env` a partir de
`.env.example`. Editá `.env` y completá `DISCORD_TOKEN` (y `DISCORD_GUILD_ID`). Después, en
dos terminales:

```powershell
.\scripts\dev.ps1 resolver
.\scripts\dev.ps1 bot
```

Probalo: entrá a un canal de voz y escribí `/play` con un link de YouTube, uno de Spotify o
el nombre de una canción.

Mientras lo usás, la PC no puede suspenderse: se cortaría la conexión de voz.

## 4. Correr con Docker

```bash
mkdir -p data/cookies && sudo chown 10001 data/cookies
docker compose up -d --build
docker compose logs -f
```

- El `chown` es necesario: el contenedor corre como usuario sin privilegios (uid 10001) y
  `yt-dlp` reescribe las cookies al refrescarlas. Con un archivo de solo lectura dejan de
  servir a los pocos días.
- El resolver **no publica ningún puerto**; solo el bot lo alcanza, dentro de la red de compose.
- Con `YTDLP_AUTO_UPDATE=true` (ya activo en el compose) el resolver busca una versión nueva
  de `yt-dlp` al arrancar y cada 24 h; si la encuentra, se reinicia solo con ella.

## 5. Cookies de YouTube (solo si hace falta)

En tu PC normalmente no hacen falta. Desde un servidor en la nube, YouTube suele responder
*"Sign in to confirm you're not a bot"*; en ese caso el bot lo avisa como `bot_detected`.

1. Creá una **cuenta de Google descartable**. Nunca uses la personal: las cookies equivalen
   a una sesión iniciada de Google, y `yt-dlp` puede hacer que YouTube sancione la cuenta.
2. En una **ventana privada**, iniciá sesión en YouTube y exportá las cookies con una
   extensión de "cookies.txt".
3. **Cerrá la ventana sin cerrar sesión**: cerrar sesión invalida las cookies exportadas.
4. Guardá el archivo como `data/cookies/cookies.txt` (Docker) o apuntá
   `YOUTUBE_COOKIES_FILE` a él (local).
5. No uses las mismas cookies desde dos IPs a la vez (tu PC y el servidor): es una señal de abuso.

Las cookies caducan; renovarlas es mantenimiento periódico.

## 6. Tus playlists de Spotify

El bot lee las playlists desde sus páginas públicas, sin credenciales. Eso implica:

1. **La playlist tiene que ser pública.** En Spotify: clic en `⋯` sobre la playlist →
   **Hacer pública**. Después copiá el link con *Compartir → Copiar enlace a la playlist* y
   usalo en `/play`. Una playlist privada responde "No encontré ese contenido en Spotify".
2. **Se leen como máximo las primeras 100 canciones.** Si tu playlist es más larga, faltan las
   últimas y el bot lo avisa ("Puede estar incompleta"). Una solución simple es dividirla en
   playlists de hasta 100.
3. **"Canciones que te gustan" no se puede usar**: Spotify no la deja compartir por link.
   Copiá esas canciones a una playlist normal.

Si necesitás playlists privadas o de más de 100 canciones, hace falta leerlas con la API de
Spotify iniciando sesión con tu cuenta. Es más trabajo y tiene sus condiciones: Spotify exige
que el dueño de la app tenga Premium, y habría que guardar un token de tu cuenta.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| El bot entra al canal pero no suena | FFmpeg no está en el `PATH` |
| Los comandos no aparecen | Falta `DISCORD_GUILD_ID`, o el bot se invitó sin `applications.commands` |
| "No puedo comunicarme con el servicio de música" | El resolver no está corriendo |
| "YouTube bloqueó la consulta…" | Detección anti-bot: cookies de cuenta descartable, o probar `YTDLP_PLAYER_CLIENT=tv,web_safari` |
| El bot arranca y se cierra | Falta `DISCORD_TOKEN`; el mensaje indica qué variable |
| Un video no suena | Privado, restringido por edad o región, o solo para miembros |
