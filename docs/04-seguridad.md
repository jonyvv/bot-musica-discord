# Datos sensibles y seguridad

Qué información sensible maneja este proyecto, dónde puede filtrarse y qué controles hay.

## Qué puede exponerse

### Crítico: dan acceso a cuentas

| Dato | Dónde puede filtrarse | Impacto |
|---|---|---|
| **Token del bot** (`DISCORD_TOKEN`) | `.env`, variables de Docker, logs, capturas, historial de git | Control total del bot en todos los servidores donde esté |
| **Cookies de YouTube/Google** (`cookies.txt`) | Archivo en disco, imagen de Docker, git | Son una **sesión iniciada de Google**: acceso a Gmail y Drive de esa cuenta, no solo a YouTube. Más grave que el token |
| **Credenciales de nube** (cuenta Oracle, clave SSH privada, `~/.oci`) | Tu PC; el repo si se copian por error | Control de la VM y de su cuenta |
| **Token de GitHub** (`gho_…`) | Keyring local. `gh auth status` lo muestra truncado | Acceso a tus repositorios |

### Alto

| Dato | Riesgo |
|---|---|
| **Historial de git** | Un secreto commiteado una vez queda en el historial aunque se borre después |
| **Capas de la imagen Docker** | Un `COPY . .` puede meter `.env` o cookies en la imagen |
| **API del resolver sin autenticación** | Si se expone el puerto, cualquiera extrae audio con **tu IP y tus cookies**, y la cuenta termina baneada |

### Medio

| Dato | Riesgo |
|---|---|
| **Mensajes de error en el canal** | Los errores se muestran en Discord, que es público |
| **URLs de stream firmadas** | Contienen tu **IP pública** y una firma válida ~6 h. FFmpeg las imprime en su stderr si falla una conexión: revisá los logs antes de compartirlos |
| **IP pública del host** | Visible para YouTube y Discord |

### Bajo

IDs de usuarios, servidor y canal en logs, y las búsquedas que escriben los usuarios (qué
escuchan) en los logs del resolver.

### Lo que este diseño evita

No hay credenciales de Spotify (se leen las páginas embed públicas), ni base de datos, ni
datos de pago, ni contraseñas de usuarios.

## Controles implementados

| Control | Dónde | Verificado por |
|---|---|---|
| `.gitignore` cubre `.env`, cookies, `data/`, `logs/`, `secrets/` | `.gitignore` | `git check-ignore` |
| El token es `SecretStr`: no aparece en `repr` ni `str` | `bot/config.py` | `test_config.py` |
| Los errores inesperados se registran pero **nunca** se muestran al usuario | `presentation/errors.py` | `test_presentation.py` |
| El error crudo de yt-dlp (puede incluir rutas) no llega al canal | `ytdlp_errors.py` | `test_ytdlp.py` |
| El resolver escucha en `127.0.0.1` por defecto y en Docker no publica puertos | `config.py`, `docker-compose.yml` | `docker compose config` |
| **Mínimo privilegio**: el resolver no recibe el token y el bot no recibe las cookies | `docker-compose.yml` | `docker compose config` |
| Contenedores sin root (uid 10001) | `Dockerfile` | — |
| `.dockerignore` excluye `.env` y cookies; el contexto de build es cada servicio, no la raíz | `services/*/.dockerignore` | — |
| El bot responde sin mencionar a nadie (`AllowedMentions.none()`) | `infrastructure/notifier.py` | `test_notifier.py` |
| Sin *intents* privilegiados: el bot no lee mensajes | `presentation/bot.py` | — |
| Una ruta de cookies inválida se ignora con aviso en vez de romper | `ytdlp_extractor.py` | `test_ytdlp.py` |

## Pendiente / a tu cargo

- [ ] Usar una **cuenta de Google descartable** para las cookies.
- [ ] Crear la app de Discord desde una cuenta que no te duela perder.
- [ ] Si el token se filtra: *Reset Token* en el portal de desarrolladores, de inmediato.
- [ ] Revisar los logs antes de compartirlos (pueden contener tu IP).
- [ ] Al desplegar en una nube: firewall que deniegue todo el tráfico entrante salvo SSH,
  acceso SSH por clave, `.env` con permisos `600`, y **no** subir de plan la cuenta
  (una cuenta Always Free de Oracle no puede generar cargos).
- [ ] Los comandos destructivos (`/stop`, `/clear`, `/leave`) los puede usar cualquiera que
  esté en el canal de voz. Es aceptable para un servidor de amigos; si el bot se abre a más
  gente, habría que agregar un rol de DJ.
