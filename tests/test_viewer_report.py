"""get_last_completed_broadcast(), get_max_concurrent_viewers(), and the
fetch_viewer_stats() orchestration that ties them together."""
import datetime
from unittest.mock import MagicMock

from googleapiclient.errors import HttpError

import handler


def make_http_error(status=500):
    resp = MagicMock(status=status, reason="error")
    return HttpError(resp, b'{"error": "boom"}', uri="https://example.com")


def broadcast(channel_id, broadcast_id, scheduled_start, title="A service"):
    return {
        "id": broadcast_id,
        "snippet": {
            "channelId": channel_id,
            "title": title,
            "scheduledStartTime": scheduled_start,
        },
    }


class TestGetLastCompletedBroadcast:
    def test_prefers_broadcast_matching_last_sunday(self):
        mock_youtube = MagicMock()
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            "items": [
                broadcast("UC_target", "old_one", "2026-05-24T11:15:00-07:00"),
                broadcast("UC_target", "the_right_one", "2026-05-31T11:15:00-07:00"),
                broadcast("UC_other_channel", "not_ours", "2026-05-31T11:15:00-07:00"),
            ]
        }

        result = handler.get_last_completed_broadcast(
            mock_youtube, "UC_target", datetime.date(2026, 5, 31)
        )

        assert result["id"] == "the_right_one"

    def test_falls_back_to_most_recent_when_no_exact_date_match(self):
        # Holiday schedule change: nothing scheduled on the expected Sunday,
        # so it should fall back to whatever's most recent overall.
        mock_youtube = MagicMock()
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            "items": [
                broadcast("UC_target", "older", "2026-05-17T11:15:00-07:00"),
                broadcast("UC_target", "most_recent", "2026-05-24T11:15:00-07:00"),
            ]
        }

        result = handler.get_last_completed_broadcast(
            mock_youtube, "UC_target", datetime.date(2026, 5, 31)
        )

        assert result["id"] == "most_recent"

    def test_returns_none_when_channel_has_no_broadcasts(self):
        mock_youtube = MagicMock()
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.return_value = {
            "items": [broadcast("UC_someone_else", "x", "2026-05-31T11:15:00-07:00")]
        }

        result = handler.get_last_completed_broadcast(
            mock_youtube, "UC_target", datetime.date(2026, 5, 31)
        )

        assert result is None

    def test_returns_none_on_api_error(self):
        mock_youtube = MagicMock()
        mock_youtube.liveBroadcasts.return_value.list.return_value.execute.side_effect = (
            make_http_error()
        )

        result = handler.get_last_completed_broadcast(
            mock_youtube, "UC_target", datetime.date(2026, 5, 31)
        )

        assert result is None


class TestGetMaxConcurrentViewers:
    def test_uses_videos_api_when_available(self):
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [{"liveStreamingDetails": {"concurrentViewers": "142"}}]
        }
        mock_analytics = MagicMock()

        result = handler.get_max_concurrent_viewers(
            mock_youtube, mock_analytics, "broadcast123", "UC_target"
        )

        assert result == 142
        mock_analytics.reports.assert_not_called()

    def test_falls_back_to_analytics_when_videos_api_has_no_data(self):
        mock_youtube = MagicMock()
        # No "concurrentViewers" key -> Attempt 1 finds nothing and falls through.
        # The same response also needs actualStartTime for Attempt 2's date range.
        mock_youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "snippet": {"publishedAt": "2026-05-31T11:15:00Z"},
                    "liveStreamingDetails": {
                        "actualStartTime": "2026-05-31T18:15:00Z",
                        "actualEndTime": "2026-05-31T19:30:00Z",
                    },
                }
            ]
        }
        mock_analytics = MagicMock()
        mock_analytics.reports.return_value.query.return_value.execute.return_value = {
            "rows": [[87]]
        }

        result = handler.get_max_concurrent_viewers(
            mock_youtube, mock_analytics, "broadcast123", "UC_target"
        )

        assert result == 87
        mock_analytics.reports.return_value.query.assert_called_once()
        call_kwargs = mock_analytics.reports.return_value.query.call_args.kwargs
        assert call_kwargs["ids"] == "channel==UC_target"
        assert call_kwargs["filters"] == "video==broadcast123"
        assert "dimensions" not in call_kwargs  # dimensions=video is unsupported here

    def test_returns_none_when_analytics_client_unavailable(self):
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [{"liveStreamingDetails": {}}]
        }

        result = handler.get_max_concurrent_viewers(
            mock_youtube, None, "broadcast123", "UC_target"
        )

        assert result is None

    def test_returns_none_when_analytics_returns_no_rows(self):
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "snippet": {"publishedAt": "2026-05-31T11:15:00Z"},
                    "liveStreamingDetails": {},
                }
            ]
        }
        mock_analytics = MagicMock()
        mock_analytics.reports.return_value.query.return_value.execute.return_value = {
            "rows": []
        }

        result = handler.get_max_concurrent_viewers(
            mock_youtube, mock_analytics, "broadcast123", "UC_target"
        )

        assert result is None

    def test_returns_none_when_attempt_two_video_lookup_finds_nothing(self):
        # Attempt 1 (concurrentViewers) comes back empty, and the follow-up
        # lookup for start/end times (Attempt 2) also finds no video at all.
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": []
        }
        mock_analytics = MagicMock()

        result = handler.get_max_concurrent_viewers(
            mock_youtube, mock_analytics, "broadcast123", "UC_target"
        )

        assert result is None
        mock_analytics.reports.assert_not_called()

    def test_returns_none_when_video_has_no_start_time_at_all(self):
        # A video with neither actualStartTime nor a snippet.publishedAt gives
        # get_max_concurrent_viewers nothing to anchor an Analytics date range on.
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.list.return_value.execute.return_value = {
            "items": [{"snippet": {}, "liveStreamingDetails": {}}]
        }
        mock_analytics = MagicMock()

        result = handler.get_max_concurrent_viewers(
            mock_youtube, mock_analytics, "broadcast123", "UC_target"
        )

        assert result is None
        mock_analytics.reports.assert_not_called()

    def test_returns_none_when_videos_api_and_analytics_both_error(self):
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.list.return_value.execute.side_effect = (
            make_http_error()
        )
        mock_analytics = MagicMock()

        result = handler.get_max_concurrent_viewers(
            mock_youtube, mock_analytics, "broadcast123", "UC_target"
        )

        assert result is None


class TestFetchViewerStats:
    def test_success_returns_status_success_with_viewer_count(
        self, monkeypatch, sample_channel
    ):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: (MagicMock(), MagicMock())
        )
        monkeypatch.setattr(
            handler,
            "get_last_completed_broadcast",
            lambda yt, cid, sunday: broadcast(
                sample_channel["channel_id"], "bcast1", "2026-05-31T11:15:00-07:00"
            ),
        )
        monkeypatch.setattr(handler, "get_max_concurrent_viewers", lambda *a: 250)

        result = handler.fetch_viewer_stats(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "success"
        assert result["max_concurrent_viewers"] == 250
        assert result["broadcast_id"] == "bcast1"
        assert result["watch_url"] == "https://www.youtube.com/watch?v=bcast1"

    def test_placeholder_channel_id_returns_error_without_any_api_call(
        self, monkeypatch, sample_channel
    ):
        sample_channel["channel_id"] = "YOUR_CHANNEL_ID_HERE"
        called = []
        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: called.append(1)
        )

        result = handler.fetch_viewer_stats(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert "not configured" in result["error"]
        assert called == []

    def test_missing_refresh_token_returns_error(self, monkeypatch, sample_channel):
        monkeypatch.delenv(sample_channel["refresh_token_env"], raising=False)

        result = handler.fetch_viewer_stats(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert sample_channel["refresh_token_env"] in result["error"]

    def test_no_completed_broadcast_returns_error(self, monkeypatch, sample_channel):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: (MagicMock(), MagicMock())
        )
        monkeypatch.setattr(
            handler, "get_last_completed_broadcast", lambda yt, cid, sunday: None
        )

        result = handler.fetch_viewer_stats(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert "No completed broadcast" in result["error"]

    def test_auth_failure_is_caught_and_reported_as_an_error(
        self, monkeypatch, sample_channel
    ):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")

        def raise_auth_error(token):
            raise RuntimeError("token expired")

        monkeypatch.setattr(handler, "get_youtube_client", raise_auth_error)

        result = handler.fetch_viewer_stats(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert "Auth failed" in result["error"]

    def test_viewer_count_unavailable_returns_error(self, monkeypatch, sample_channel):
        monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-token")
        monkeypatch.setattr(
            handler, "get_youtube_client", lambda token: (MagicMock(), MagicMock())
        )
        monkeypatch.setattr(
            handler,
            "get_last_completed_broadcast",
            lambda yt, cid, sunday: broadcast(
                sample_channel["channel_id"], "bcast1", "2026-05-31T11:15:00-07:00"
            ),
        )
        monkeypatch.setattr(handler, "get_max_concurrent_viewers", lambda *a: None)

        result = handler.fetch_viewer_stats(
            "test_channel", sample_channel, datetime.date(2026, 5, 31)
        )

        assert result["status"] == "error"
        assert "not yet available" in result["error"]
