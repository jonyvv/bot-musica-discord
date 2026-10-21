class BotError(Exception):
    def __init__(self, user_message: str):
        """Crea un error cuyo mensaje se puede mostrar tal cual al usuario."""
        super().__init__(user_message)
        self.user_message = user_message


class ResolverError(BotError):
    def __init__(self, user_message: str, code: str = "resolver_error"):
        """Crea un error devuelto por el servicio de resolución, con su código estable."""
        super().__init__(user_message)
        self.code = code


class ResolverUnavailableError(ResolverError):
    pass


class InvalidRequestError(BotError):
    pass


class NotPlayingError(BotError):
    pass


class VoiceError(BotError):
    pass
