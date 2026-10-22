# Documentación

| Documento | Contenido |
|---|---|
| [01-requisitos.md](01-requisitos.md) | Requisitos funcionales y no funcionales, restricciones técnicas, análisis de hosting y de la detección de bots de YouTube. Escrito antes de construir: ver el aviso al inicio |
| [02-arquitectura.md](02-arquitectura.md) | Diseño de los dos servicios, contrato HTTP, concurrencia y **qué cambió respecto de los requisitos** |
| [03-setup.md](03-setup.md) | Crear la app de Discord, correr en local y con Docker, cookies de YouTube, playlists de Spotify, problemas frecuentes |
| [04-seguridad.md](04-seguridad.md) | Ataques considerados, cómo se probaron, qué encontraron y qué se corrigió |
| [05-despliegue-nube.md](05-despliegue-nube.md) | Publicar en Oracle Cloud Always Free con la configuración más segura; qué está verificado y qué no |

## Estado

La implementación está completa y probada con tests, contra YouTube y Spotify reales y en Docker real.

Pendiente, porque requiere cosas que solo vos tenés:

- La primera ejecución contra un servidor de Discord real (necesita tu token).
- El despliegue en la VM de Oracle y, antes que nada, comprobar que `yt-dlp` puede bajar audio desde su
  IP ([05-despliegue-nube.md](05-despliegue-nube.md), paso 7).
