class ResolverError(Exception):
    code = "resolver_error"

    def __init__(self, message: str):
        """Crea el error con un mensaje apto para mostrar al usuario final."""
        super().__init__(message)
        self.message = message


class UnsupportedInputError(ResolverError):
    code = "unsupported_input"


class TrackNotFoundError(ResolverError):
    code = "not_found"


class TrackUnavailableError(ResolverError):
    code = "unavailable"


class BotDetectedError(ResolverError):
    code = "bot_detected"


class SpotifyUnavailableError(ResolverError):
    code = "spotify_unavailable"


class UpstreamError(ResolverError):
    code = "upstream_error"


class UnauthorizedError(ResolverError):
    code = "unauthorized"


class RateLimitedError(ResolverError):
    code = "rate_limited"

    def __init__(self, message: str, retry_after: float = 1.0):
        """Crea el error de exceso de pedidos junto con los segundos que conviene esperar."""
        super().__init__(message)
        self.retry_after = retry_after
