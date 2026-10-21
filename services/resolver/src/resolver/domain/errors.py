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
