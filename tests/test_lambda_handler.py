"""lambda_handler() — the top-level orchestrator. Every worker function it calls
(fetch_viewer_stats, schedule_next_event, send_to_sheet, send_email) is mocked
out here; their real behavior is covered in their own test modules. This file
is only about the wiring: which mode/channel/dry_run combination calls what."""
import datetime
from unittest.mock import MagicMock

import handler


def make_fake_channels():
    return {
        "chan_a": {"label": "Channel A", "create_events": True},
        "chan_b": {"label": "Channel B", "create_events": True},
    }


def install_common_mocks(monkeypatch, mocker):
    monkeypatch.setattr(handler, "CHANNELS", make_fake_channels())
    monkeypatch.setattr(
        handler, "get_last_sunday", lambda: datetime.date(2026, 5, 31)
    )
    monkeypatch.setattr(
        handler, "get_next_sunday", lambda: datetime.date(2026, 6, 7)
    )
    fetch_mock = mocker.patch(
        "handler.fetch_viewer_stats",
        return_value={"status": "success", "max_concurrent_viewers": 10},
    )
    schedule_mock = mocker.patch(
        "handler.schedule_next_event", return_value={"status": "created"}
    )
    sheet_mock = mocker.patch(
        "handler.send_to_sheet", return_value={"status": "sent"}
    )
    email_mock = mocker.patch("handler.send_email", return_value=True)
    mocker.patch("handler.build_email", return_value=("subject", "<html></html>"))
    return fetch_mock, schedule_mock, sheet_mock, email_mock


class TestLambdaHandler:
    def test_default_event_runs_both_tasks_for_every_channel(self, monkeypatch, mocker):
        fetch_mock, schedule_mock, sheet_mock, email_mock = install_common_mocks(
            monkeypatch, mocker
        )

        response = handler.lambda_handler({}, None)

        assert response["statusCode"] == 200
        assert fetch_mock.call_count == 2
        assert schedule_mock.call_count == 2
        sheet_mock.assert_called_once()
        email_mock.assert_called_once()

    def test_dry_run_skips_sheet_sync_and_email_but_still_creates_events(
        self, monkeypatch, mocker
    ):
        fetch_mock, schedule_mock, sheet_mock, email_mock = install_common_mocks(
            monkeypatch, mocker
        )

        handler.lambda_handler({"dry_run": True}, None)

        assert schedule_mock.call_count == 2
        for call in schedule_mock.call_args_list:
            assert call.args[-1] is True  # dry_run propagated through
        sheet_mock.assert_not_called()
        email_mock.assert_not_called()

    def test_single_channel_filter_only_processes_that_channel(self, monkeypatch, mocker):
        fetch_mock, schedule_mock, sheet_mock, email_mock = install_common_mocks(
            monkeypatch, mocker
        )

        handler.lambda_handler({"channel": "chan_a"}, None)

        assert fetch_mock.call_count == 1
        assert fetch_mock.call_args.args[0] == "chan_a"
        assert schedule_mock.call_count == 1
        # Single-channel runs never send an email...
        email_mock.assert_not_called()
        # ...but the sheet sync condition doesn't check target_channel at all,
        # so it still fires. Documented here since it's easy to assume otherwise.
        sheet_mock.assert_called_once()

    def test_viewer_report_mode_skips_event_creation(self, monkeypatch, mocker):
        fetch_mock, schedule_mock, sheet_mock, email_mock = install_common_mocks(
            monkeypatch, mocker
        )

        handler.lambda_handler({"mode": "viewer_report"}, None)

        assert fetch_mock.call_count == 2
        schedule_mock.assert_not_called()
        sheet_mock.assert_called_once()
        email_mock.assert_called_once()

    def test_create_events_mode_skips_viewer_report_and_sheet_sync(
        self, monkeypatch, mocker
    ):
        fetch_mock, schedule_mock, sheet_mock, email_mock = install_common_mocks(
            monkeypatch, mocker
        )

        handler.lambda_handler({"mode": "create_events"}, None)

        fetch_mock.assert_not_called()
        assert schedule_mock.call_count == 2
        sheet_mock.assert_not_called()
        email_mock.assert_not_called()

    def test_channel_level_create_events_false_is_respected(self, monkeypatch, mocker):
        channels = make_fake_channels()
        channels["chan_b"]["create_events"] = False
        monkeypatch.setattr(handler, "CHANNELS", channels)
        monkeypatch.setattr(handler, "get_last_sunday", lambda: datetime.date(2026, 5, 31))
        monkeypatch.setattr(handler, "get_next_sunday", lambda: datetime.date(2026, 6, 7))
        mocker.patch(
            "handler.fetch_viewer_stats",
            return_value={"status": "success", "max_concurrent_viewers": 10},
        )
        schedule_mock = mocker.patch(
            "handler.schedule_next_event", return_value={"status": "created"}
        )
        mocker.patch("handler.send_to_sheet", return_value={"status": "sent"})
        mocker.patch("handler.send_email", return_value=True)
        mocker.patch("handler.build_email", return_value=("subject", "<html></html>"))

        handler.lambda_handler({}, None)

        assert schedule_mock.call_count == 1
        assert schedule_mock.call_args.args[0] == "chan_a"

    def test_response_body_summary_reflects_mocked_results(self, monkeypatch, mocker):
        monkeypatch.setattr(handler, "CHANNELS", make_fake_channels())
        monkeypatch.setattr(handler, "get_last_sunday", lambda: datetime.date(2026, 5, 31))
        monkeypatch.setattr(handler, "get_next_sunday", lambda: datetime.date(2026, 6, 7))
        mocker.patch(
            "handler.fetch_viewer_stats",
            side_effect=[
                {"status": "success", "max_concurrent_viewers": 10},
                {"status": "error", "error": "boom"},
            ],
        )
        mocker.patch(
            "handler.schedule_next_event",
            side_effect=[{"status": "created"}, {"status": "error"}],
        )
        mocker.patch("handler.send_to_sheet", return_value={"status": "sent"})
        mocker.patch("handler.send_email", return_value=True)
        mocker.patch("handler.build_email", return_value=("subject", "<html></html>"))

        response = handler.lambda_handler({}, None)

        import json

        body = json.loads(response["body"])
        assert body["summary"]["viewer_report"] == {"success": 1, "errors": 1}
        assert body["summary"]["event_creation"] == {"success": 1, "errors": 1}
        assert body["summary"]["last_sunday"] == "2026-05-31"
        assert body["summary"]["next_sunday"] == "2026-06-07"
