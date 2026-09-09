import base64
import hashlib
from unittest.mock import MagicMock

import pytest

from onyx.llm.aipg import image_recovery

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5ioAAAAASUVORK5CYII="
)


def result() -> dict:
    return {
        "media": [
            {
                "url": "https://example.test/test.png",
                "key": "test.png",
                "sha256": hashlib.sha256(PNG).hexdigest(),
            }
        ],
        "model": "Krea 2 Turbo",
        "worker": "test",
        "gen_time": 1.0,
    }


@pytest.fixture
def download(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    get = MagicMock()
    response = get.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_content.return_value = [PNG]
    monkeypatch.setattr(image_recovery, "ssrf_safe_get", get)
    return get


def test_download_is_integrity_checked_and_has_no_service_credentials(
    download: MagicMock,
) -> None:
    assert base64.b64decode(image_recovery.image_base64(result())) == PNG
    assert download.call_args.kwargs == {
        "timeout": 30,
        "follow_redirects": False,
        "stream": True,
    }


def test_corrupt_image_is_not_shown(download: MagicMock) -> None:
    download.return_value.__enter__.return_value.iter_content.return_value = [
        b"wrong image"
    ]
    with pytest.raises(image_recovery.GridImageRecoveryError, match="integrity"):
        image_recovery.image_base64(result())


def test_image_download_is_bounded(download: MagicMock) -> None:
    download.return_value.__enter__.return_value.iter_content.return_value = [
        b"x" * (20 * 1024 * 1024 + 1)
    ]
    with pytest.raises(image_recovery.GridImageRecoveryError, match="limit"):
        image_recovery.image_base64(result())


def test_redirected_asset_is_not_followed(download: MagicMock) -> None:
    response = download.return_value.__enter__.return_value
    response.status_code = 302
    with pytest.raises(image_recovery.GridImageRecoveryError, match="unavailable"):
        image_recovery.image_base64(result())
    response.iter_content.assert_not_called()
