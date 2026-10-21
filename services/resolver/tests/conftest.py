import pytest

from resolver.domain.models import Source, Track


@pytest.fixture
def make_track():
    def factory(title="Song", duration=200, url="https://www.youtube.com/watch?v=abc", **extra):
        return Track(
            title=title,
            artist=extra.pop("artist", "Artist"),
            duration_seconds=duration,
            source=extra.pop("source", Source.YOUTUBE),
            webpage_url=url,
            **extra,
        )

    return factory
