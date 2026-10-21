# Documentación

| Documento | Contenido |
|---|---|
| [01-requisitos.md](01-requisitos.md) | Requisitos funcionales y no funcionales, restricciones técnicas, análisis de hosting y de la detección de bots de YouTube. Escrito antes de construir: ver el aviso al inicio |
| [02-arquitectura.md](02-arquitectura.md) | Diseño de los dos servicios, contrato HTTP, concurrencia y **qué cambió respecto de los requisitos** |
| [03-setup.md](03-setup.md) | Crear la app de Discord, correr en local y con Docker, cookies de YouTube, problemas frecuentes |
| [04-seguridad.md](04-seguridad.md) | Datos sensibles que maneja el proyecto, dónde pueden filtrarse y qué controles hay |

## Estado

La implementación está completa y probada con tests y contra YouTube y Spotify reales.
Pendiente: la primera ejecución contra un servidor de Discord real (requiere un token) y la
construcción de las imágenes de Docker.

El despliegue en la nube (Oracle Cloud Always Free) está analizado en la sección 9 del
documento 01 pero **no se encaró**: la primera versión corre en local. Antes de portarlo,
conviene el *spike* de la sección 9.3.8: verificar a mano que `yt-dlp` puede bajar audio
desde la IP del servidor.
