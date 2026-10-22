"""Ataques de prueba contra un resolver desplegado, para verificar que las defensas funcionan."""

import argparse
import asyncio
import json
import socket
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

CANARY = "/tmp/pwned_by_attack"
VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
SSRF_TARGETS = [
    "http://169.254.169.254/latest/meta-data/",
    "http://169.254.169.254/opc/v2/instance/",
    "http://localhost:8080/health",
    "http://127.0.0.1:22/",
    "http://[::1]/",
    "http://resolver:8080/health",
    "http://metadata.google.internal/computeMetadata/v1/",
    "file:///etc/passwd",
    "file:///run/secrets/resolver_api_key_sha256",
    "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
    "https://evil.example/watch?v=dQw4w9WgXcQ",
    "https://user:pass@www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com:8443/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/redirect?v=dQw4w9WgXcQ&q=http://169.254.169.254/",
    "https://www.youtube.com\\@evil.example/watch?v=dQw4w9WgXcQ",
    "http://0x7f000001/",
    "http://2130706433/",
    "gopher://127.0.0.1:6379/_PING",
    "-f lavfi -i anullsrc",
]
QUERY_PAYLOADS = [
    f"rick astley; touch {CANARY}",
    f"$(touch {CANARY})",
    f"`touch {CANARY}`",
    f"x\ntouch {CANARY}",
    f'x" && touch {CANARY} && echo "',
    f"--exec touch {CANARY}",
    "--config-locations /etc/passwd",
    "ytsearchall:rick astley",
    "ytsearch9999:rick astley",
    "../../../../etc/passwd",
    "\x00\x00null",
    "%00%0a%0d",
    "A" * 450,
    "‮​‍﻿",
]


@dataclass(slots=True)
class Result:
    attack: str
    defended: bool
    detail: str


class Target:
    def __init__(self, base: str, key: str):
        """Destino de los ataques y la clave válida que se usa para simular a un insider."""
        self.base = base.rstrip("/")
        self.key = key
        parsed = urlparse(self.base)
        self.host, self.port = parsed.hostname, parsed.port or 80
        self.duration = 20.0
        self.offline = False

    def client(self, **kwargs) -> httpx.AsyncClient:
        """Crea un cliente HTTP apuntando al destino."""
        return httpx.AsyncClient(base_url=self.base, timeout=kwargs.pop("timeout", 30), **kwargs)

    def auth(self) -> dict[str, str]:
        """Header con la clave válida."""
        return {"Authorization": f"Bearer {self.key}"}

    async def healthy(self) -> bool:
        """Indica si el servicio sigue respondiendo a su chequeo de salud."""
        try:
            async with self.client(timeout=5) as client:
                return (await client.get("/health")).status_code == 200
        except httpx.HTTPError:
            return False

    async def raw(self, payload: bytes, wait: float = 3.0) -> bytes:
        """Envía bytes crudos por un socket y devuelve lo que responda el servidor."""

        def exchange() -> bytes:
            with socket.create_connection((self.host, self.port), timeout=wait) as sock:
                sock.sendall(payload)
                try:
                    return sock.recv(65536)
                except OSError:
                    return b""

        return await asyncio.to_thread(exchange)


def status_line(data: bytes) -> str:
    """Primera línea de una respuesta HTTP cruda."""
    return data.split(b"\r\n", 1)[0].decode(errors="replace") or "(sin respuesta)"


async def recon(t: Target) -> list[Result]:
    """Reconocimiento: rutas expuestas, documentación y cabeceras que delaten el software."""
    out = []
    async with t.client() as c:
        for path in [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/admin",
            "/.env",
            "/metrics",
            "/v1/",
            "/%2e%2e/%2e%2e/etc/passwd",
        ]:
            r = await c.get(path)
            out.append(
                Result(f"recon GET {path}", r.status_code in (404, 405), f"HTTP {r.status_code}")
            )
        r = await c.get("/health")
        leaks = [h for h in ("server", "x-powered-by") if h in r.headers]
        out.append(
            Result(
                "recon: cabeceras que revelan el software",
                not leaks,
                f"expuestas: {leaks or 'ninguna'}",
            )
        )
        r = await c.post("/v1/resolve", json={"query": "x"})
        leaked = any(w in r.text for w in ("Traceback", "/app/", "site-packages", 'File "'))
        out.append(Result("recon: errores sin rastros internos", not leaked, r.text[:80]))
    return out


async def injection(t: Target) -> list[Result]:
    """Inyección: SSRF por URLs hostiles y comandos del sistema dentro de las búsquedas."""
    out = []
    async with t.client(headers=t.auth()) as c:
        for url in SSRF_TARGETS:
            track = {"title": "x", "source": "youtube", "webpage_url": url}
            started = time.perf_counter()
            r = await c.post("/v1/stream", json=track)
            code = (
                r.json().get("code")
                if r.headers.get("content-type", "").startswith("application/json")
                else "?"
            )
            fast = time.perf_counter() - started < 1.5
            out.append(
                Result(
                    f"ssrf stream {url[:55]}",
                    r.status_code == 422 and fast,
                    f"HTTP {r.status_code} {code}",
                )
            )
        for payload in [] if t.offline else QUERY_PAYLOADS:
            r = await c.post("/v1/resolve", json={"query": payload})
            tracks = r.json().get("tracks", []) if r.status_code == 200 else []
            ok = r.status_code != 500 and len(tracks) <= 1
            out.append(
                Result(
                    f"inyeccion query {payload[:40]!r}",
                    ok,
                    f"HTTP {r.status_code}, {len(tracks)} pista(s)",
                )
            )
    return out


async def abuse_input(t: Target) -> list[Result]:
    """Entradas deformadas: JSON roto, tipos erróneos, bombas de anidamiento y HTTP inválido."""
    out = []
    bodies = {
        "json roto": b'{"query": ',
        "no es objeto": b"[1,2,3]",
        "tipo erroneo": b'{"query": {"a": 1}}',
        "numero enorme": b'{"query": 1' + b"0" * 5000 + b"}",
        "bomba de anidamiento": b"[" * 30000 + b"]" * 30000,
        "claves duplicadas": b'{"query": "a", "query": "b"}',
        "campos extra": b'{"query": "a", "__proto__": {"x": 1}, "admin": true}',
        "unicode invalido": b'{"query": "\\ud800"}',
        "vacio": b"",
    }
    async with t.client(headers={**t.auth(), "Content-Type": "application/json"}) as c:
        for name, body in bodies.items():
            r = await c.post("/v1/resolve", content=body)
            out.append(Result(f"entrada: {name}", r.status_code != 500, f"HTTP {r.status_code}"))
        r = await c.post("/v1/resolve", content=b"x" * 10_000_000)
        out.append(Result("cuerpo de 10 MB", r.status_code == 413, f"HTTP {r.status_code}"))
        r = await c.post("/v1/resolve", json={"query": "a"}, headers={"X-Big": "h" * 60000})
        out.append(Result("cabecera de 60 KB", r.status_code != 500, f"HTTP {r.status_code}"))
    raw = {
        "linea de pedido de 100 KB": b"GET /" + b"a" * 100_000 + b" HTTP/1.1\r\nHost: x\r\n\r\n",
        "metodo invalido": b"BREW /health HTTP/1.1\r\nHost: x\r\n\r\n",
        "CL y TE a la vez (smuggling)": b"POST /v1/resolve HTTP/1.1\r\nHost: x\r\nContent-Length: 4\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
        "Content-Length negativo": b"POST /v1/resolve HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n",
        "HTTP/9.9": b"GET /health HTTP/9.9\r\nHost: x\r\n\r\n",
        "basura binaria": bytes(range(256)) * 20,
    }
    for name, payload in raw.items():
        line = status_line(await t.raw(payload))
        rejected = any(
            code in line
            for code in ("400", "431", "414", "405", "411", "413", "426", "505", "(sin respuesta)")
        )
        answered_as_1_1 = name == "HTTP/9.9" and line.startswith("HTTP/1.1")
        out.append(
            Result(f"http crudo: {name}", rejected or answered_as_1_1 or "200" not in line, line)
        )
    out.append(Result("servicio vivo tras las entradas deformadas", await t.healthy(), ""))
    return out


async def flood(t: Target) -> list[Result]:
    """Inundación: miles de pedidos simultáneos para saturar CPU, memoria o conexiones."""
    counts: dict[str, int] = {}
    latencies: list[float] = []
    hostile = {"title": "x", "source": "youtube", "webpage_url": SSRF_TARGETS[0]}
    path, body = ("/v1/stream", hostile) if t.offline else ("/v1/resolve", {"query": VIDEO})
    limits = httpx.Limits(max_connections=150, max_keepalive_connections=0)
    async with t.client(headers=t.auth(), limits=limits, timeout=60) as c:
        gate = asyncio.Semaphore(120)

        async def one(i: int) -> None:
            async with gate:
                started = time.perf_counter()
                try:
                    r = await c.post(path, json=body)
                    key = str(r.status_code)
                except httpx.HTTPError as exc:
                    key = type(exc).__name__
                latencies.append(time.perf_counter() - started)
                counts[key] = counts.get(key, 0) + 1

        started = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(3000)))
        elapsed = time.perf_counter() - started
    served = counts.get("200", 0)
    limited = counts.get("429", 0)
    dropped = sum(v for k, v in counts.items() if k.endswith("Error"))
    errors = counts.get("500", 0)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    return [
        Result(
            "flood 3000 pedidos: todo el exceso se rechaza (429, 503 o conexion cortada)",
            limited + counts.get("503", 0) + dropped >= 3000 - 130,
            f"{counts} en {elapsed:.1f}s",
        ),
        Result("flood: solo se atiende hasta el cupo", served <= 130, f"200 = {served}"),
        Result("flood: sin errores de servidor", errors == 0, f"errores = {errors}"),
        Result("flood: rechazar es rapido (p95)", p95 < 5, f"p95 = {p95 * 1000:.0f} ms"),
        Result("flood: el servicio sigue vivo", await t.healthy(), ""),
    ]


async def probe(t: Target) -> list[Result]:
    """Cliente legítimo: pide el servicio cada 200 ms mientras otro contenedor inunda."""
    statuses: dict[str, int] = {}
    latencies: list[float] = []
    deadline = time.monotonic() + t.duration
    async with t.client(headers=t.auth(), timeout=30) as c:
        while time.monotonic() < deadline:
            started = time.perf_counter()
            try:
                key = str((await c.post("/v1/resolve", json={"query": VIDEO})).status_code)
            except httpx.HTTPError as exc:
                key = type(exc).__name__
            latencies.append(time.perf_counter() - started)
            statuses[key] = statuses.get(key, 0) + 1
            await asyncio.sleep(0.2)
    total = sum(statuses.values())
    ok = statuses.get("200", 0)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    return [
        Result(
            "disponibilidad bajo ataque: cliente legitimo atendido",
            ok / total >= 0.9,
            f"{ok}/{total} OK, {statuses}",
        ),
        Result("disponibilidad bajo ataque: latencia p95", p95 < 2, f"p95 = {p95 * 1000:.0f} ms"),
    ]


async def bruteforce(t: Target) -> list[Result]:
    """Fuerza bruta: adivinar la clave de la API hasta que el servicio bloquee al atacante."""
    statuses: list[int] = []
    async with t.client() as c:
        for i in range(60):
            r = await c.post(
                "/v1/resolve", json={"query": "x"}, headers={"Authorization": f"Bearer guess-{i}"}
            )
            statuses.append(r.status_code)
        with_real = await c.post("/v1/resolve", json={"query": "x"}, headers=t.auth())
    locked_at = next((i for i, s in enumerate(statuses) if s == 429), None)
    return [
        Result(
            "fuerza bruta: bloqueo del atacante tras pocos intentos",
            locked_at is not None and locked_at <= 6,
            f"429 desde el intento {locked_at}",
        ),
        Result(
            "fuerza bruta: ningun intento falso entra",
            200 not in statuses,
            f"estados = {sorted(set(statuses))}",
        ),
        Result(
            "fuerza bruta: ni la clave real pasa desde la IP bloqueada",
            with_real.status_code == 429,
            f"HTTP {with_real.status_code}",
        ),
    ]


async def slowloris(t: Target) -> list[Result]:
    """Slowloris: cientos de conexiones abiertas que mandan los headers a cuentagotas."""
    opened = []
    for _ in range(400):
        try:
            sock = await asyncio.to_thread(socket.create_connection, (t.host, t.port), 3)
            sock.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\nX-Slow: ")
            opened.append(sock)
        except OSError:
            break
    await asyncio.sleep(2)
    survivors = 0
    for sock in opened:
        sock.settimeout(0.05)
        try:
            survivors += sock.recv(1) != b""
        except TimeoutError:
            survivors += 1
        except OSError:
            pass
    for sock in opened:
        sock.close()
    await asyncio.sleep(1)
    return [
        Result(
            "slowloris: el servidor limita las conexiones colgadas de una IP",
            survivors <= 40,
            f"{len(opened)} abiertas, siguen vivas {survivors}",
        ),
        Result("slowloris: el servicio responde al cerrarlas", await t.healthy(), ""),
    ]


async def heavy(t: Target) -> list[Result]:
    """Carga pesada válida: búsquedas distintas a la vez, que no se pueden resolver desde la caché."""
    queries = [f"cancion de prueba numero {i} {time.time()}" for i in range(40)]
    health_during: list[bool] = []
    limits = httpx.Limits(max_connections=12)
    async with t.client(headers=t.auth(), timeout=120, limits=limits) as c:

        async def watch() -> None:
            for _ in range(10):
                health_during.append(await t.healthy())
                await asyncio.sleep(1)

        started = time.perf_counter()
        results, _ = await asyncio.gather(
            asyncio.gather(*(c.post("/v1/resolve", json={"query": q}) for q in queries)), watch()
        )
        elapsed = time.perf_counter() - started
    statuses = sorted({r.status_code for r in results})
    rate = len(queries) / elapsed
    return [
        Result(
            "carga pesada: el servicio responde mientras trabaja",
            all(health_during),
            f"{sum(health_during)}/{len(health_during)} chequeos",
        ),
        Result(
            "carga pesada: hacia YouTube se va espaciado",
            rate < 8,
            f"{len(queries)} busquedas en {elapsed:.1f}s ({rate:.1f}/s)",
        ),
        Result(
            "carga pesada: sin errores de servidor",
            all(s < 500 or s == 503 for s in statuses),
            f"estados = {statuses}",
        ),
    ]


async def legit(t: Target) -> list[Result]:
    """Control: un cliente legítimo sigue pudiendo usar el servicio tras los ataques."""
    async with t.client(headers=t.auth(), timeout=60) as c:
        r = await c.post("/v1/resolve", json={"query": VIDEO})
    ok = r.status_code == 200 and r.json()["tracks"]
    return [Result("control: cliente legitimo atendido", bool(ok), f"HTTP {r.status_code}")]


GROUPS: dict[str, Callable[[Target], Awaitable[list[Result]]]] = {
    "recon": recon,
    "injection": injection,
    "abuse_input": abuse_input,
    "flood": flood,
    "probe": probe,
    "bruteforce": bruteforce,
    "slowloris": slowloris,
    "heavy": heavy,
    "legit": legit,
}


async def run(groups: list[str], target: Target) -> int:
    """Ejecuta los grupos pedidos, imprime cada resultado y devuelve cuántos ataques tuvieron éxito."""
    failures = 0
    for name in groups:
        print(f"\n== {name} ==")
        try:
            results = await GROUPS[name](target)
        except Exception as exc:
            results = [Result(f"{name}: la prueba falló", False, f"{type(exc).__name__}: {exc}")]
        for result in results:
            failures += not result.defended
            print(
                f"{'DEFENDIDO' if result.defended else 'VULNERABLE'} | {result.attack} | {result.detail}"
            )
    return failures


def main() -> None:
    """Punto de entrada: lee destino y clave, corre los ataques y sale con error si alguno prosperó."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://resolver:8080")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--only", default=",".join(GROUPS), help="grupos separados por comas")
    parser.add_argument("--duration", type=float, default=20.0, help="segundos del grupo probe")
    parser.add_argument("--offline", action="store_true", help="no depende de YouTube (para CI)")
    args = parser.parse_args()
    target = Target(args.base, args.key_file.read_text().strip())
    target.duration = args.duration
    target.offline = args.offline
    failures = asyncio.run(run(args.only.split(","), target))
    print(json.dumps({"ataques_exitosos": failures}))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
