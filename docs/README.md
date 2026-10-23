# Documentación

| Documento | Contenido |
|---|---|
| [01-requisitos.md](01-requisitos.md) | Requisitos funcionales y no funcionales, restricciones técnicas, análisis de hosting y de la detección de bots de YouTube. Escrito antes de construir: ver el aviso al inicio |
| [02-arquitectura.md](02-arquitectura.md) | Diseño de los dos servicios, contrato HTTP, concurrencia y **qué cambió respecto de los requisitos** |
| [03-setup.md](03-setup.md) | Crear la app de Discord, correr en local y con Docker, cookies de YouTube, playlists de Spotify, problemas frecuentes |
| [04-seguridad.md](04-seguridad.md) | Ataques considerados, cómo se probaron, qué encontraron y qué se corrigió |
| [05-despliegue-nube.md](05-despliegue-nube.md) | Publicar en Oracle Cloud Always Free con la configuración más segura; qué está verificado y qué no |

## Estado

La implementación está completa y probada con tests, contra YouTube y Spotify reales, en Docker real y
en un servidor de Discord real corriendo en Windows (comandos, voz y reproducción).

Pendiente, porque requiere cosas que solo vos tenés:

- Desplegarlo en un servidor propio. Hace falta un host con tarjeta (Oracle) o aceptar un VPS gratuito de
  terceros; antes que nada, comprobar que `yt-dlp` puede bajar audio desde su IP
  ([05-despliegue-nube.md](05-despliegue-nube.md), paso 7).
- Probar el bot en Docker contra Discord (hasta ahora solo corrió así el resolver).
