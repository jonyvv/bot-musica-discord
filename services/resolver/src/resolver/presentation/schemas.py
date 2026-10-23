from pydantic import BaseModel, ConfigDict, Field, field_validator

from resolver.domain.models import CollectionKind, Resolution, Source, StreamInfo, Track


def encodable(value: str | None) -> str | None:
    """Rechaza textos con caracteres Unicode inválidos que no se pueden codificar en UTF-8."""
    if value is not None:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("contiene caracteres inválidos") from exc
    return value


class ResolveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

    _valid_text = field_validator("query")(encodable)


class TrackSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(max_length=1000)
    artist: str | None = Field(default=None, max_length=1000)
    duration_seconds: int | None = Field(default=None, ge=0, le=172_800)
    source: Source
    webpage_url: str | None = Field(default=None, max_length=2048)
    search_query: str | None = Field(default=None, max_length=1200)
    thumbnail_url: str | None = Field(default=None, max_length=2048)
    is_live: bool = False

    _valid_text = field_validator(
        "title", "artist", "webpage_url", "search_query", "thumbnail_url"
    )(encodable)

    def to_domain(self) -> Track:
        """Convierte el esquema recibido en una canción del dominio."""
        return Track(**self.model_dump())


class ResolutionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: CollectionKind
    title: str | None
    tracks: list[TrackSchema]
    truncated: bool

    @classmethod
    def from_domain(cls, resolution: Resolution) -> "ResolutionSchema":
        """Construye el esquema de respuesta a partir de una resolución del dominio."""
        return cls.model_validate(resolution)


class StreamSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    headers: dict[str, str]
    expires_at: int | None
    webpage_url: str

    @classmethod
    def from_domain(cls, stream: StreamInfo) -> "StreamSchema":
        """Construye el esquema de respuesta a partir de un stream del dominio."""
        return cls.model_validate(stream)


class ErrorSchema(BaseModel):
    code: str
    message: str
