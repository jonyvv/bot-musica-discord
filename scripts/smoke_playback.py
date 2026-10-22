"""Verifica que el audio se puede reproducir: resuelve, pide el stream y lo decodifica."""

import argparse
import asyncio
import sys

import discord
import httpx

from bot.config import Settings
from bot.domain.errors import BotError
from bot.domain.models import Track
from bot.infrastructure.ffmpeg import before_options
from bot.infrastructure.resolver_client import HttpTrackResolver
from bot.main import resolver_headers

FRAME_SECONDS = 0.02
DEFAULT_QUERY = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


async def decode(resolver: HttpTrackResolver, track: Track, seconds: float) -> float:
    """Pide el audio de una canción y devuelve cuántos segundos logra decodificar FFmpeg."""
    stream = await resolver.stream(track)
    source = discord.FFmpegPCMAudio(
        stream.url, before_options=before_options(stream.headers), options="-vn"
    )
    frames = 0
    while frames * FRAME_SECONDS < seconds and source.read():
        frames += 1
    source.cleanup()
    return frames * FRAME_SECONDS


async def check(query: str, seconds: float, limit: int) -> list[bool]:
    """Prueba las primeras `limit` canciones de la consulta e imprime el resultado de cada una."""
    settings = Settings()
    results = []
    async with httpx.AsyncClient(
        base_url=settings.resolver_url, timeout=120, headers=resolver_headers(settings)
    ) as http:
        resolver = HttpTrackResolver(http)
        for track in (await resolver.resolve(query)).tracks[:limit]:
            name = f"{track.artist} - {track.title}"[:70]
            try:
                decoded = await decode(resolver, track, seconds)
            except BotError as exc:
                print(f"FALLA: {name} | {exc.user_message}")
                results.append(False)
                continue
            ok = decoded >= seconds * 0.9
            print(f"{'OK' if ok else 'FALLA'}: {name} | {decoded:.1f} s de {seconds:.1f} s")
            results.append(ok)
    return results


def main() -> None:
    """Punto de entrada: sale con error si alguna canción no se pudo decodificar."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queries", nargs="*", default=[DEFAULT_QUERY])
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--limit", type=int, default=1, help="canciones a probar por consulta")
    args = parser.parse_args()
    results = [r for q in args.queries for r in asyncio.run(check(q, args.seconds, args.limit))]
    print(f"{sum(results)}/{len(results)} canciones reproducibles")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
