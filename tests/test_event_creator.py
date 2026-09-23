"""create_live_event() (the two-call insert+bind sequence) and
schedule_next_event() (the orchestration around it, including the dry_run guard)."""
import datetime
from unittest.mock import MagicMock

from googleapiclient.errors import HttpError

import handler


def make_http_error(status=500):
    resp = MagicMock(status=status, reason="error")
    return HttpError(resp, b'{"error": "boom"}', uri="https://example.com")


class TestCreateLiveEvent:
    def test_inserts_then_binds_to_the_persistent_stream(self):
        mock_youtube = MagicMock()
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "new_broadcast_id"
        }
        start_time = handler.make_stream_datetime(datetime.date(2026, 5, 31), 11, 15)

        result = handler.create_live_event(
            youtube=mock_youtube,
            channel_id="UC_target",
            stream_id="stream_abc",
            title="Test Service – May 31, 2026",
            start_time=start_time,
            privacy="public",
            description="A description",
            enable_embed=True,
        )

        assert result["status"] == "created"
        assert result["broadcast_id"] == "new_broadcast_id"
        assert result["watch_url"] == "https://www.youtube.com/watch?v=new_broadcast_id"

        insert_kwargs = mock_youtube.liveBroadcasts.return_value.insert.call_args.kwargs
        assert insert_kwargs["body"]["snippet"]["title"] == "Test Service – May 31, 2026"
        assert insert_kwargs["body"]["snippet"]["channelId"] == "UC_target"
        assert insert_kwargs["body"]["status"]["privacyStatus"] == "public"
        assert insert_kwargs["body"]["contentDetails"]["enableEmbed"] is True

        mock_youtube.liveBroadcasts.return_value.bind.assert_called_once_with(
            part="id,contentDetails", id="new_broadcast_id", streamId="stream_abc"
        )

    def test_enable_embed_false_is_passed_through(self):
        mock_youtube = MagicMock()
        mock_youtube.liveBroadcasts.return_value.insert.return_value.execute.return_value = {
            "id": "bcast"
        }
        start_time = handler.make_stream_datetime(datetime.date(2026, 5, 31), 9, 30)

        handler.create_live_event(
            youtube=mock_youtube,
            channel_id="UC_target",
            stream_id="stream_abc",
            title="Title",
            start_time=start_time,
            privacy="public",
            description="desc",
            enable_embed=False,
        )

        insert_kwargs = mock_youtube.liveBroadcasts.return_value.insert.call_args.kwargs
        assert insert_kwargs["body"]["contentDetails"]["enableEmbed"] is False


class TestScheduleNextEvent:
    def test_dry_run_never_calls_the_youtube_api(self, monkeypatch, sample_channel):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setenv(sample_channel["stream_id_env"], "fake-stream-id")

        called = []
        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: called.append(1)
        )

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31), dry_run=True
        )

        assert result["status"] == "dry_run"
        assert result["title"] == "Test Service – May 31, 2026"
        assert called == []  # the whole point of dry_run: zero live API calls

    def test_missing_refresh_token_is_an_error_and_skips_api_calls(
        self, monkeypatch, sample_channel
    ):
        monkeypatch.delenv(sample_channel["refresh_token_env"], raising=False)
        monkeypatch.setenv(sample_channel["stream_id_env"], "fake-stream-id")

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert sample_channel["refresh_token_env"] in result["error"]

    def test_missing_stream_id_is_an_error(self, monkeypatch, sample_channel):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.delenv(sample_channel["stream_id_env"], raising=False)

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert sample_channel["stream_id_env"] in result["error"]

    def test_placeholder_channel_id_is_an_error(self, monkeypatch, sample_channel):
        sample_channel["channel_id"] = "YOUR_CHANNEL_ID_HERE"

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert "not configured" in result["error"]

    def test_success_uploads_thumbnail_and_adds_to_playlist(
        self, monkeypatch, sample_channel
    ):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setenv(sample_channel["stream_id_env"], "fake-stream-id")
        monkeypatch.setenv("EVENTS_S3_BUCKET", "my-bucket")

        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: (MagicMock(), MagicMock())
        )
        monkeypatch.setattr(
            handler,
            "create_live_event",
            lambda **kwargs: {
                "status": "created",
                "broadcast_id": "bcast1",
                "stream_id": kwargs["stream_id"],
                "watch_url": "https://www.youtube.com/watch?v=bcast1",
                "title": kwargs["title"],
                "start_time": kwargs["start_time"].isoformat(),
            },
        )
        monkeypatch.setattr(handler, "upload_thumbnail", lambda **kwargs: True)
        monkeypatch.setattr(handler, "add_to_playlist", lambda **kwargs: True)

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "created"
        assert result["thumbnail_uploaded"] is True
        assert result["playlist_added"] is True
        assert result["channel"] == "test_channel"

    def test_no_playlist_id_configured_skips_playlist_step(
        self, monkeypatch, sample_channel
    ):
        sample_channel["playlist_id"] = ""
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setenv(sample_channel["stream_id_env"], "fake-stream-id")

        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: (MagicMock(), MagicMock())
        )
        monkeypatch.setattr(
            handler,
            "create_live_event",
            lambda **kwargs: {
                "status": "created",
                "broadcast_id": "bcast1",
                "stream_id": kwargs["stream_id"],
                "watch_url": "https://www.youtube.com/watch?v=bcast1",
                "title": kwargs["title"],
                "start_time": kwargs["start_time"].isoformat(),
            },
        )
        monkeypatch.setattr(handler, "upload_thumbnail", lambda **kwargs: False)

        called = []
        monkeypatch.setattr(
            handler, "add_to_playlist", lambda **kwargs: called.append(1)
        )

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["playlist_added"] is False
        assert called == []

    def test_youtube_api_error_during_creation_is_caught_and_reported(
        self, monkeypatch, sample_channel
    ):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setenv(sample_channel["stream_id_env"], "fake-stream-id")

        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: (MagicMock(), MagicMock())
        )

        def raise_http_error(**kwargs):
            raise make_http_error()

        monkeypatch.setattr(handler, "create_live_event", raise_http_error)

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert result["channel"] == "test_channel"

    def test_unexpected_error_during_creation_is_also_caught_and_reported(
        self, monkeypatch, sample_channel
    ):
        # A second, separate except clause below the HttpError one — needs its
        # own trigger (a plain exception, not an HttpError) to exercise.
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setenv(sample_channel["stream_id_env"], "fake-stream-id")

        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: (MagicMock(), MagicMock())
        )

        def raise_runtime_error(**kwargs):
            raise RuntimeError("something unrelated to the YouTube API broke")

        monkeypatch.setattr(handler, "create_live_event", raise_runtime_error)

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert "unrelated to the YouTube API" in result["error"]

    def test_auth_failure_is_caught_and_reported(self, monkeypatch, sample_channel):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setenv(sample_channel["stream_id_env"], "fake-stream-id")

        def raise_auth_error(token):
            raise RuntimeError("token expired")

        monkeypatch.setattr(handler, "get_youtube_client", raise_auth_error)

        result = handler.schedule_next_event(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert "Auth failed" in result["error"]
