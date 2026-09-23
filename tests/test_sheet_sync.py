"""send_to_sheet() — POSTs successful viewer counts to the Apps Script Web App.
No real HTTP calls: urllib.request.urlopen is mocked at the boundary."""
import datetime
import json
from unittest.mock import MagicMock

import handler


def success_result(channel="ms_channel", viewers=142):
    return {"status": "success", "channel": channel, "max_concurrent_viewers": viewers}


def error_result(channel="ss_channel"):
    return {"status": "error", "channel": channel, "error": "No completed broadcast found"}


class TestSendToSheet:
    def test_skips_when_webapp_url_not_configured(self, monkeypatch, mocker):
        monkeypatch.delenv("SHEET_WEBAPP_URL", raising=False)
        monkeypatch.setenv("SHEET_WEBAPP_SECRET", "shh")
        mock_urlopen = mocker.patch("handler.urllib.request.urlopen")

        result = handler.send_to_sheet([success_result()], datetime.date(2026, 5, 31))

        assert result == {"status": "skipped", "reason": "not configured"}
        mock_urlopen.assert_not_called()

    def test_skips_when_secret_not_configured(self, monkeypatch, mocker):
        monkeypatch.setenv("SHEET_WEBAPP_URL", "https://script.google.com/exec")
        monkeypatch.delenv("SHEET_WEBAPP_SECRET", raising=False)
        mock_urlopen = mocker.patch("handler.urllib.request.urlopen")

        result = handler.send_to_sheet([success_result()], datetime.date(2026, 5, 31))

        assert result == {"status": "skipped", "reason": "not configured"}
        mock_urlopen.assert_not_called()

    def test_skips_when_no_successful_results(self, monkeypatch, mocker):
        monkeypatch.setenv("SHEET_WEBAPP_URL", "https://script.google.com/exec")
        monkeypatch.setenv("SHEET_WEBAPP_SECRET", "shh")
        mock_urlopen = mocker.patch("handler.urllib.request.urlopen")

        result = handler.send_to_sheet([error_result()], datetime.date(2026, 5, 31))

        assert result == {"status": "skipped", "reason": "no successful results"}
        mock_urlopen.assert_not_called()

    def test_only_successful_results_are_sent_in_the_payload(self, monkeypatch, mocker):
        monkeypatch.setenv("SHEET_WEBAPP_URL", "https://script.google.com/exec")
        monkeypatch.setenv("SHEET_WEBAPP_SECRET", "correct-secret")

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok", "outcomes": []}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen = mocker.patch(
            "handler.urllib.request.urlopen", return_value=mock_response
        )

        viewer_results = [
            success_result("ms_channel", 142),
            error_result("ss_channel"),
            success_result("es_channel", 87),
        ]

        result = handler.send_to_sheet(viewer_results, datetime.date(2026, 5, 31))

        assert result["status"] == "sent"

        sent_request = mock_urlopen.call_args.args[0]
        payload = json.loads(sent_request.data)

        assert payload["secret"] == "correct-secret"
        channels_sent = {r["channel"] for r in payload["results"]}
        assert channels_sent == {"ms_channel", "es_channel"}
        assert all(r["date"] == "2026-05-31" for r in payload["results"])

    def test_url_error_returns_error_status_not_raise(self, monkeypatch, mocker):
        import urllib.error

        monkeypatch.setenv("SHEET_WEBAPP_URL", "https://script.google.com/exec")
        monkeypatch.setenv("SHEET_WEBAPP_SECRET", "shh")
        mocker.patch(
            "handler.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        )

        result = handler.send_to_sheet([success_result()], datetime.date(2026, 5, 31))

        assert result["status"] == "error"
