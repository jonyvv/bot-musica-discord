from pydantic import BaseModel, ConfigDict, Field

from resolver.domain.models import CollectionKind, Resolution, Source, StreamInfo, Track


class ResolveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class TrackSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    artist: str | None = None
    duration_seconds: int | None = None
    source: Source
    webpage_url: str | None = None
    search_query: str | None = None
    thumbnail_url: str | None = None
    is_live: bool = False

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
