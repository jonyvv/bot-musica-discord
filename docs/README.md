# Documentación — Bot de música para Discord

Índice de la documentación del proyecto. Todo documento nuevo va en esta carpeta,
numerado, y se agrega acá.

| Documento | Estado | Contenido |
|---|---|---|
| [01-requisitos.md](01-requisitos.md) | v1.3 — requisitos cerrados, listo para arrancar | Requisitos funcionales y no funcionales, restricciones técnicas, hosting, arquitectura propuesta, criterios de aceptación y plan por fases |

## Alcance de la v1

**Funcionalidad completa corriendo en la PC, con Python nativo y sin Docker.** La
migración a la nube queda documentada pero se hace después (fases 8 y 9 del §12).

## Decisiones tomadas

- **Stack:** Python 3.11+ con discord.py 2.x, `yt-dlp` y FFmpeg en un solo proceso.
- **Escala:** un solo servidor de Discord (uso con amigos) ⇒ un stream de audio máximo.
- **Hosting v1:** la PC del usuario, Windows, venv. Gratis, sin tarjeta, iteración
  inmediata, y la IP residencial evita el riesgo técnico #1.
- **Hosting futuro:** Oracle Cloud Always Free, instancia ARM `A1.Flex`. Costo cero
  estricto: la cuenta **no se upgradea nunca**, y así no puede generar cargos.
- **Audio:** volumen instantáneo (`PCMVolumeTransformer`) en local; el perfil de Oracle
  también lo soporta, así que migrar no obliga a degradar.
- **Dependencias del sistema:** FFmpeg **y un runtime de JavaScript** (Deno o Node),
  que `yt-dlp` ya necesita para resolver los desafíos de YouTube.
- **Riesgo de ToS** de §6.1: aceptado.

## Pendientes de documentar

- `02-arquitectura.md` — diseño detallado de módulos
- `03-setup.md` — crear la app de Discord, obtener el token y las credenciales de
  Spotify, instalar FFmpeg y Deno en Windows, y levantar el venv
- `04-deploy.md` — solo cuando se encare la nube (fases 8 y 9)

## Notas importantes

**El problema de YouTube queda escondido en la v1** (§9.4.3). En local, con IP
residencial, la detección de bots casi no aparece — así que la v1 va a funcionar perfecto
**sin demostrar nada** sobre si funcionará en la nube. El riesgo no se resuelve, se
posterga. Por eso:

- La fase 8 es un **spike** separado de la 9: media hora de prueba manual decide si
  Oracle sirve, **antes** de invertir trabajo en portar el bot (RNF-47).
- Las medidas de la capa 1 de §9.3.3 se implementan igual en la v1 (`yt-dlp` al día,
  runtime de JS, cliente de player configurable). No cuestan nada en local y son lo que
  la fase 8 va a necesitar.

**Spotify no se puede reproducir directamente** (§6.1). Se resuelve vía metadatos de la
API de Spotify + búsqueda del equivalente en YouTube, con las implicancias de ToS que
están documentadas ahí y que el usuario aceptó.

**La §9.3 se verificó en octubre de 2026** contra la wiki de yt-dlp, hilos de GitHub y
foros. Dos hallazgos que corrigen versiones anteriores de este documento: los PO token ya
no son la solución principal, y `yt-dlp` ahora necesita un runtime de JavaScript. Fuentes
citadas en §9.3.12; conviene revalidar antes de la fase 8.

**Vercel no puede hostear este bot** (§9.1.2): es serverless, sin proceso persistente ni
UDP de salida. **Google Cloud quedó descartado** (§9.2.1) porque su free tier factura el
excedente de egreso en silencio.
