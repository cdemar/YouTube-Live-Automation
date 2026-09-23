"""build_email() (pure HTML string building) and send_email() (SES wrapper)."""
import datetime
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

import handler


def success_viewer_result(label="Mandarin", viewers=142):
    return {
        "status": "success",
        "channel": "ms_channel",
        "label": label,
        "broadcast_id": "bcast1",
        "broadcast_title": "Sunday Service",
        "stream_date": "2026-05-31",
        "watch_url": "https://www.youtube.com/watch?v=bcast1",
        "max_concurrent_viewers": viewers,
    }


def error_viewer_result(label="Spanish", error="No completed broadcast found"):
    return {"status": "error", "channel": "ss_channel", "label": label, "error": error}


def created_event_result(label="Mandarin"):
    return {
        "status": "created",
        "channel": "ms_channel",
        "label": label,
        "broadcast_id": "bcast2",
        "watch_url": "https://www.youtube.com/watch?v=bcast2",
        "title": "Sunday Service – June 7, 2026",
        "start_time": "2026-06-07T11:15:00-07:00",
        "thumbnail_uploaded": True,
        "playlist_added": True,
    }


class TestBuildEmail:
    def test_all_successful_reports_all_ok_in_subject(self):
        subject, html = handler.build_email(
            [success_viewer_result()],
            [created_event_result()],
            datetime.date(2026, 5, 31),
            datetime.date(2026, 6, 7),
        )

        assert "All channels completed successfully" in subject
        assert "142" in html
        assert "Mandarin" in html

    def test_a_failed_channel_flips_subject_to_issues_and_shows_error_text(self):
        subject, html = handler.build_email(
            [success_viewer_result(), error_viewer_result()],
            [created_event_result()],
            datetime.date(2026, 5, 31),
            datetime.date(2026, 6, 7),
        )

        assert "Some channels had issues" in subject
        assert "No completed broadcast found" in html

    def test_dry_run_event_result_renders_without_watch_url_key(self):
        # dry_run results don't carry a "watch_url" key at all — build_email
        # must not KeyError on that.
        dry_run_result = {
            "status": "dry_run",
            "channel": "ms_channel",
            "label": "Mandarin",
            "title": "Sunday Service – June 7, 2026",
            "start_time": "2026-06-07T11:15:00-07:00",
            "thumbnail_s3_key": "thumbnails/mandarin.jpeg",
            "note": "Dry run",
        }

        subject, html = handler.build_email(
            [], [dry_run_result], datetime.date(2026, 5, 31), datetime.date(2026, 6, 7)
        )

        assert "🔄" in html

    def test_failed_event_result_shows_its_error_text(self):
        failed_event = {
            "status": "error",
            "channel": "ss_channel",
            "label": "Spanish",
            "error": "Missing env var: SS_STREAM_ID",
        }

        subject, html = handler.build_email(
            [success_viewer_result()],
            [created_event_result(), failed_event],
            datetime.date(2026, 5, 31),
            datetime.date(2026, 6, 7),
        )

        assert "Some channels had issues" in subject
        assert "Missing env var: SS_STREAM_ID" in html

    def test_empty_result_lists_do_not_raise(self):
        subject, html = handler.build_email(
            [], [], datetime.date(2026, 5, 31), datetime.date(2026, 6, 7)
        )
        assert "All channels completed successfully" in subject


class TestSendEmail:
    def test_success_calls_ses_with_correct_source_and_destination(
        self, monkeypatch, mocker
    ):
        monkeypatch.setenv("SES_FROM_EMAIL", "noreply@example.org")
        monkeypatch.setenv("SES_TO_EMAIL", "staff@example.org")
        monkeypatch.setenv("SES_REGION", "us-west-2")

        mock_ses = MagicMock()
        mock_boto_client = mocker.patch.object(handler.boto3, "client", return_value=mock_ses)

        result = handler.send_email("Subject line", "<html></html>")

        assert result is True
        mock_boto_client.assert_called_once_with("ses", region_name="us-west-2")
        call_kwargs = mock_ses.send_email.call_args.kwargs
        assert call_kwargs["Source"] == "noreply@example.org"
        assert call_kwargs["Destination"] == {"ToAddresses": ["staff@example.org"]}
        assert call_kwargs["Message"]["Subject"]["Data"] == "Subject line"

    def test_defaults_to_us_west_2_when_ses_region_not_set(self, monkeypatch, mocker):
        monkeypatch.setenv("SES_FROM_EMAIL", "noreply@example.org")
        monkeypatch.setenv("SES_TO_EMAIL", "staff@example.org")
        monkeypatch.delenv("SES_REGION", raising=False)

        mock_boto_client = mocker.patch.object(
            handler.boto3, "client", return_value=MagicMock()
        )

        handler.send_email("Subject", "<html></html>")

        mock_boto_client.assert_called_once_with("ses", region_name="us-west-2")

    def test_ses_client_error_returns_false_not_raise(self, monkeypatch, mocker):
        monkeypatch.setenv("SES_FROM_EMAIL", "noreply@example.org")
        monkeypatch.setenv("SES_TO_EMAIL", "staff@example.org")

        mock_ses = MagicMock()
        mock_ses.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "boom"}}, "SendEmail"
        )
        mocker.patch.object(handler.boto3, "client", return_value=mock_ses)

        result = handler.send_email("Subject", "<html></html>")

        assert result is False

    def test_missing_recipient_env_vars_raises_keyerror_uncaught(
        self, monkeypatch, mocker
    ):
        # Documents current behavior, not necessarily desired behavior: every
        # other failure path in this file (S3, YouTube, the Sheet webhook)
        # degrades gracefully and returns False/None. This one doesn't — a
        # missing SES_FROM_EMAIL/SES_TO_EMAIL bypasses the `except ClientError`
        # entirely and propagates a raw KeyError, because os.environ[...] is
        # evaluated inside the try block but only ClientError is caught there.
        monkeypatch.delenv("SES_FROM_EMAIL", raising=False)
        monkeypatch.delenv("SES_TO_EMAIL", raising=False)
        mocker.patch.object(handler.boto3, "client", return_value=MagicMock())

        with pytest.raises(KeyError):
            handler.send_email("Subject", "<html></html>")
