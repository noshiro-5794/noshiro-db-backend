from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from integrations.storage.minio import MinioClient


def test_minio_sdk_client_is_created_lazily() -> None:
    with patch("integrations.storage.minio.Minio") as minio_factory:
        client = MinioClient()

        minio_factory.assert_not_called()

        assert client.client is minio_factory.return_value
        assert client.client is minio_factory.return_value
        minio_factory.assert_called_once_with(
            "127.0.0.1:9000",
            access_key="test",
            secret_key="test",
            secure=False,
        )


@override_settings(MINIO_ENDPOINT=None)
def test_minio_configuration_is_validated_on_first_use() -> None:
    client = MinioClient()

    with pytest.raises(ImproperlyConfigured, match="MINIO_ENDPOINT"):
        _ = client.client


def test_minio_public_url_does_not_initialize_sdk_client() -> None:
    with patch("integrations.storage.minio.Minio") as minio_factory:
        client = MinioClient()

        assert client.get_file_url("avatars/example.webp") == (
            "http://127.0.0.1:9000/test/avatars/example.webp"
        )
        minio_factory.assert_not_called()


def test_delete_public_url_removes_only_owned_bucket_objects() -> None:
    sdk_client = Mock()
    client = MinioClient(client=sdk_client)
    client._bucket_ready = True

    assert client.delete_public_url("http://127.0.0.1:9000/test/avatars/example.webp")
    sdk_client.remove_object.assert_called_once_with(
        "test",
        "avatars/example.webp",
    )

    sdk_client.reset_mock()
    assert not client.delete_public_url(
        "http://127.0.0.1:9000/other/avatars/example.webp"
    )
    sdk_client.remove_object.assert_not_called()
