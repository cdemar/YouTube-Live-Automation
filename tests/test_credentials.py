"""get_refresh_token() and get_youtube_client() — the AUTH section of handler.py."""
import logging

import handler


class TestGetYoutubeClient:
    def test_builds_data_and_analytics_clients_from_a_refreshed_credential(
        self, monkeypatch, mocker
    ):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-client-id")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-client-secret")

        mock_creds_instance = mocker.MagicMock()
        mock_creds_class = mocker.patch.object(
            handler, "Credentials", return_value=mock_creds_instance
        )
        mock_build = mocker.patch.object(
            handler, "build", side_effect=["fake-youtube-client", "fake-analytics-client"]
        )

        youtube, analytics = handler.get_youtube_client("fake-refresh-token")

        assert youtube == "fake-youtube-client"
        assert analytics == "fake-analytics-client"
        mock_creds_class.assert_called_once_with(
            token=None,
            refresh_token="fake-refresh-token",
            client_id="fake-client-id",
            client_secret="fake-client-secret",
            token_uri="https://oauth2.googleapis.com/token",
            scopes=[
                "https://www.googleapis.com/auth/youtube",
                "https://www.googleapis.com/auth/yt-analytics.readonly",
            ],
        )
        mock_creds_instance.refresh.assert_called_once()
        assert mock_build.call_args_list[0].args[0] == "youtube"
        assert mock_build.call_args_list[1].args[0] == "youtubeAnalytics"


def test_returns_token_when_env_var_set(monkeypatch, sample_channel):
    monkeypatch.setenv(sample_channel["refresh_token_env"], "fake-refresh-token")
    assert handler.get_refresh_token(sample_channel) == "fake-refresh-token"


def test_returns_none_when_env_var_missing(monkeypatch, sample_channel):
    monkeypatch.delenv(sample_channel["refresh_token_env"], raising=False)
    assert handler.get_refresh_token(sample_channel) is None


def test_logs_error_when_env_var_missing(monkeypatch, sample_channel, caplog):
    monkeypatch.delenv(sample_channel["refresh_token_env"], raising=False)
    with caplog.at_level(logging.ERROR):
        handler.get_refresh_token(sample_channel)
    assert sample_channel["refresh_token_env"] in caplog.text
