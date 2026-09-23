import pytest


@pytest.fixture
def sample_channel():
    """A minimal channel config shaped like an entry in handler.CHANNELS.

    Deliberately not imported from handler.CHANNELS itself — tests should keep
    working even if the real channel list changes.
    """
    return {
        "label": "Test Channel",
        "title_prefix": "Test Service",
        "description": "Test description",
        "channel_id": "UCtestChannelId00000000",
        "stream_id_env": "TEST_STREAM_ID",
        "refresh_token_env": "TEST_REFRESH_TOKEN",
        "stream_hour": 11,
        "stream_minute": 15,
        "privacy": "public",
        "thumbnail_s3_key": "thumbnails/test.jpeg",
        "playlist_id": "PLtestPlaylistId00000000",
    }
