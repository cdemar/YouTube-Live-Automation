"""upload_thumbnail() and add_to_playlist() — both non-fatal helpers that return
a bool rather than raising, so a failure here never takes down the whole run."""
from unittest.mock import ANY, MagicMock

from googleapiclient.errors import HttpError

import handler


class FakeNoSuchKey(Exception):
    """Stand-in for the real boto3 client's dynamically-generated NoSuchKey
    exception class, which only exists on a real client instance."""


def make_http_error(status=500):
    resp = MagicMock(status=status, reason="error")
    return HttpError(resp, b'{"error": "boom"}', uri="https://example.com")


def make_fake_s3():
    """A MagicMock S3 client with a real exception class wired up at
    .exceptions.NoSuchKey. Every test that patches handler.s3 needs this —
    the `except s3.exceptions.NoSuchKey:` clause in upload_thumbnail() has to
    resolve to a real BaseException subclass to type-check at all, even when
    the exception actually raised is something else entirely."""
    mock_s3 = MagicMock()
    mock_s3.exceptions.NoSuchKey = FakeNoSuchKey
    return mock_s3


class TestUploadThumbnail:
    def test_success_uploads_bytes_from_s3_to_youtube(self, monkeypatch):
        mock_s3 = make_fake_s3()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"fake-jpeg-bytes"),
            "ContentType": "image/jpeg",
        }
        monkeypatch.setattr(handler, "s3", mock_s3)

        mock_youtube = MagicMock()

        result = handler.upload_thumbnail(
            mock_youtube, "broadcast123", "my-bucket", "thumbnails/test.jpeg"
        )

        assert result is True
        mock_s3.get_object.assert_called_once_with(
            Bucket="my-bucket", Key="thumbnails/test.jpeg"
        )
        mock_youtube.thumbnails.return_value.set.assert_called_once_with(
            videoId="broadcast123", media_body=ANY
        )

    def test_missing_file_in_s3_returns_false_not_raise(self, monkeypatch):
        mock_s3 = make_fake_s3()
        mock_s3.get_object.side_effect = FakeNoSuchKey()
        monkeypatch.setattr(handler, "s3", mock_s3)

        result = handler.upload_thumbnail(
            MagicMock(), "broadcast123", "my-bucket", "thumbnails/missing.jpeg"
        )

        assert result is False

    def test_youtube_api_error_returns_false_not_raise(self, monkeypatch):
        mock_s3 = make_fake_s3()
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"bytes"),
            "ContentType": "image/jpeg",
        }
        monkeypatch.setattr(handler, "s3", mock_s3)

        mock_youtube = MagicMock()
        mock_youtube.thumbnails.return_value.set.return_value.execute.side_effect = (
            make_http_error()
        )

        result = handler.upload_thumbnail(
            mock_youtube, "broadcast123", "my-bucket", "thumbnails/test.jpeg"
        )

        assert result is False

    def test_unexpected_error_returns_false_not_raise(self, monkeypatch):
        mock_s3 = make_fake_s3()
        mock_s3.get_object.side_effect = RuntimeError("network blip")
        monkeypatch.setattr(handler, "s3", mock_s3)

        result = handler.upload_thumbnail(
            MagicMock(), "broadcast123", "my-bucket", "thumbnails/test.jpeg"
        )

        assert result is False


class TestAddToPlaylist:
    def test_success_inserts_video_into_playlist(self):
        mock_youtube = MagicMock()

        result = handler.add_to_playlist(mock_youtube, "PLxyz", "broadcast123")

        assert result is True
        mock_youtube.playlistItems.return_value.insert.assert_called_once_with(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": "PLxyz",
                    "resourceId": {"kind": "youtube#video", "videoId": "broadcast123"},
                }
            },
        )

    def test_api_error_returns_false_not_raise(self):
        mock_youtube = MagicMock()
        mock_youtube.playlistItems.return_value.insert.return_value.execute.side_effect = (
            make_http_error()
        )

        result = handler.add_to_playlist(mock_youtube, "PLxyz", "broadcast123")

        assert result is False
