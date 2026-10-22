# Seguridad

Qué ataques se consideraron, cómo se probaron y qué se corrigió. Todo lo que dice "probado" se
ejecutó contra el código o contra contenedores reales de Docker.

## Los ataques comunes a bots de música en la nube

| # | Ataque | Defensas | Probado con |
|---|---|---|---|
| 1 | **Robo del token** y secuestro del bot | Secretos fuera de git y de variables de entorno; `SecretStr`; token cifrado en tu PC; escáner de secretos en CI; permisos mínimos | Tests + `docker inspect` + búsqueda del token en logs, entorno y procesos |
| 2 | **Denegación de servicio** (listas gigantes, audio infinito, inundación) | Tope de playlist, de cola y por usuario; sin transmisiones en vivo; duración máxima; límites de tasa y de simultaneidad | 3000 pedidos simultáneos; 400 conexiones colgadas |
| 3 | **Inyección** en comandos (`!play URL; rm -rf /`) | Sin shell; la URL se reconstruye a partir del ID; FFmpeg solo admite http(s) | 20 SSRF + 14 cargas de inyección + canario de ejecución |
| 4 | **Bloqueo de IP** por scraping | Caché con consulta única, espaciado, tope de simultáneas y cortacircuito | Carga con 40 búsquedas distintas |

### 1. Robo del token

- **No se hashea**: un hash es de una sola vía y el token hay que *presentárselo* a Discord. El hash se
  usa donde corresponde: la clave bot → resolver se guarda solo como SHA-256 y se compara en tiempo
  constante.
- El token vive en el **Administrador de credenciales de Windows** (cifrado con tu usuario) o en un
  **secreto de Docker** (archivo `0400`, no variable de entorno). Verificado: no aparece en el entorno,
  en la línea de comandos de los procesos, en la salida del bot, en `docker inspect` ni en `compose config`.
- El resolver (que procesa links no confiables) **no recibe el token**; el bot **no recibe las cookies**.
- **Radio de daño limitado**: el bot se invita solo con conectar, hablar, enviar mensajes e insertar
  enlaces. Con un token robado no se puede banear a nadie, porque ese permiso nunca se concedió.
  Además avisa en el log si en algún servidor le dieron permisos de más.
- El bot **solo opera en los servidores permitidos** y se retira de los demás.
- `tests/test_no_secrets.py` escanea todo el repositorio buscando la forma de un token, y falla el CI.

### 2. Denegación de servicio

| Vector | Defensa | Resultado probado |
|---|---|---|
| Playlist enorme | Máximo 500 canciones por pedido, 1000 en cola y 200 por usuario | Aplicado |
| Audio infinito | Se rechazan las transmisiones en vivo y lo que dura más de 3 h | Aplicado en la lista y al pedir el audio |
| Inundación de pedidos | 120/min por cliente, 16 en curso por cliente; el resto recibe 429 | 3000 pedidos: 120 atendidos, 2880 rechazados, 0 errores |
| Inundación vs. cliente legítimo | Límite por IP, no global | El cliente legítimo siguió al **100 %** (57/57, 18 ms) mientras otro inundaba |
| Slowloris | Plazo de 10 s para los headers, plazo para el cuerpo, 32 conexiones por IP | Con 400 conexiones colgadas, otro cliente recibió 200 en ~70 ms |
| Cuerpos enormes | Máximo 64 KB; también si llegan en trozos sin `Content-Length` | 10 MB → 413 |
| Fuerza bruta a la clave | Bloqueo tras 5 intentos inválidos | Bloqueado en el intento 5, también con la clave real desde esa IP |
| Comandos en ráfaga | 8 por usuario y 30 por servidor cada 10 s; 3 resoluciones simultáneas | Aplicado |

### 3. Inyección

- yt-dlp se usa como **librería**, nunca como un comando de shell, así que `; rm -rf /` no ejecuta nada.
- Las URLs no se validan: se **reconstruyen**. Se extrae el ID de video (11 caracteres) y se arma
  `https://www.youtube.com/watch?v=ID`. A yt-dlp nunca le llega texto del usuario, lo que elimina de raíz
  el SSRF (`169.254.169.254`, `localhost`, `user@host`, puertos, `\`, redirecciones).
- La URL de audio que devuelve yt-dlp también se verifica: solo `https` y dominios de YouTube.
- FFmpeg corre con `-protocol_whitelist http,https,tcp,tls,crypto`: `file:`, `concat:` y `data:` quedan
  bloqueados (probado en el contenedor). Las cabeceras se escapan y se verificó que ninguna puede
  inyectar un argumento.
- Los títulos y artistas externos se limpian (control, dirección de texto, comillas invertidas) y se
  escapan al mostrarlos, para que un video llamado `[gratis](http://malo) @everyone` no sea un enlace
  ni una mención. El bot no menciona a nadie.

### 4. Bloqueo de IP

- **Caché** de 10 minutos y **consulta única**: 200 pedidos iguales a la vez producen una sola consulta a YouTube.
- Espaciado de 0,3 s y máximo 3 consultas simultáneas (40 búsquedas distintas: 3,9/s).
- **Cortacircuito**: tras 3 detecciones de bot seguidas deja de consultar 10 minutos. Insistir
  empeora el bloqueo.
- Verificación de cada URL con el mismo pedido que hace FFmpeg antes de entregarla y de cachearla,
  con caída al siguiente cliente de YouTube si falla.
- En tu PC (IP residencial) casi no ocurre; en la nube es el riesgo principal. Ver [05](05-despliegue-nube.md).

## Otros ataques considerados

| Ataque | Defensa |
|---|---|
| **ReDoS** (regex que se cuelgan) | El filtro de logs tenía un patrón cuadrático que colgaba el servicio con 100 000 caracteres; ahora es lineal y hay un test de tiempo |
| **Falsificar el log** con saltos de línea | El filtro los neutraliza |
| **Revelar el software** | Sin cabecera `Server`, sin `/docs` ni `/openapi.json` |
| **Fuga de entrada** en los errores | Los 422 listan los campos que fallaron, nunca lo que mandó el cliente |
| **Invitar el bot a otros servidores** | Lista permitida; sale solo |
| **Cadena de suministro** | Versiones exactas, `pip-audit`, Dependabot, imágenes base fijadas por *digest*, acciones de CI fijadas por SHA, escaneo con Trivy, CodeQL |
| **Escape del contenedor** | Sin root, sin capacidades, `no-new-privileges`, bot de solo lectura, límites de memoria y procesos, sin montar el socket de Docker |
| **Secretos en la imagen** | `.dockerignore`, contexto por servicio y escaneo de secretos de Trivy |

## Qué encontraron las pruebas (y se corrigió)

Estas pruebas son las que encontraron problemas reales; ninguno se habría visto leyendo el código:

1. El resolver pedía a yt-dlp **cualquier URL** (incluido el servicio de metadatos de la nube) y su API no exigía clave.
2. Un carácter Unicode inválido hacía **fallar la respuesta de error** y se devolvía lo que mandó el atacante.
3. Un **ReDoS** cuadrático en el filtro de logs.
4. Una inundación desde una IP dejaba a los **clientes legítimos con 503** (24 % de fallos).
5. **400 conexiones a medio abrir** tumbaban el servicio entero.
6. El `.gitignore` no cubría `*.pem` ni `*.key`.
7. El compose compartía todo el `.env`: el resolver recibía el token de Discord.
8. **PyNaCl 1.5.0** tenía CVE-2025-69277 (se actualizó y se comprobó byte a byte que el cifrado de voz no cambia).
9. Al quitar `discord.py[voice]` se perdió **`davey`** (cifrado de voz DAVE): sin él la voz no funciona en Docker.
10. El cliente de YouTube por defecto de yt-dlp entrega URLs que **FFmpeg rechaza con 403**; el bot no habría reproducido nada.
11. Los errores crudos de yt-dlp llegaban al canal público de Discord (podían incluir rutas).
12. Una ruta de cookies inválida rompía consultas que habían salido bien.

## Datos sensibles y dónde pueden filtrarse

| Dato | Dónde | Impacto |
|---|---|---|
| Token del bot | `.env`, variables de entorno, logs, capturas, historial de git | Control del bot en sus servidores |
| Cookies de Google | Archivo en disco, imagen, git | Es una **sesión de Google**: acceso a Gmail y Drive. Por eso, cuenta descartable |
| Credenciales de nube y claves SSH | Tu PC, el repo si se copian | Control de la VM |
| Token de GitHub | Almacén local; `gh auth status` lo muestra truncado | Acceso a tus repos |
| URLs de stream | Logs de FFmpeg | Contienen tu **IP pública** y una firma válida ~6 h |

El repositorio es **público**: todo lo que se sube lo ve cualquiera. Los commits muestran el nombre y
el correo de tu configuración de git.

## Qué no cubre el código (tareas tuyas)

Ver el checklist de [05-despliegue-nube.md](05-despliegue-nube.md): MFA en todas las cuentas, cuenta de
Google descartable para las cookies, SSH solo desde tu IP, *Public Bot* desactivado, y activar *Secret
scanning* y *Push protection* en GitHub.

## Cómo repetir las pruebas

```bash
scripts/audit_containers.sh              # 30 comprobaciones de endurecimiento
scripts/attack_compose.sh                # ataques contra el resolver desplegado
scripts/attack_compose.sh --offline      # sin depender de YouTube (lo que corre en CI)
python scripts/smoke_playback.py URL     # el audio realmente se decodifica
```
