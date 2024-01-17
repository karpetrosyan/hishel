import typing as tp
from datetime import datetime, timedelta, timezone

from anyio import to_thread


class S3Manager:
    def __init__(self, client: tp.Any, bucket_name: str, is_binary: bool = False):
        self._client = client
        self._bucket_name = bucket_name
        self._is_binary = is_binary

    def write_to(self, path: str, data: tp.Union[bytes, str]) -> None:
        path = "hishel-" + path
        if isinstance(data, str):
            data = data.encode("utf-8")

        self._client.put_object(Bucket=self._bucket_name, Key=path, Body=data)

    def read_from(self, path: str) -> tp.Union[bytes, str]:
        path = "hishel-" + path
        response = self._client.get_object(
            Bucket=self._bucket_name,
            Key=path,
        )

        content = response["Body"].read()

        if self._is_binary:  # pragma: no cover
            return tp.cast(bytes, content)

        return tp.cast(str, content.decode("utf-8"))

    def remove_expired(self, ttl: int) -> None:
        for obj in self._client.list_objects(Bucket=self._bucket_name).get("Contents", []):
            if not obj["Key"].startswith("hishel-"):  # pragma: no cover
                continue

            if datetime.now(timezone.utc) - obj["LastModified"] > timedelta(milliseconds=ttl):
                self._client.delete_object(Bucket=self._bucket_name, Key=obj["Key"])


class AsyncS3Manager:
    def __init__(self, client: tp.Any, bucket_name: str, is_binary: bool = False):
        self._sync_manager = S3Manager(client, bucket_name, is_binary)

    async def write_to(self, path: str, data: tp.Union[bytes, str]) -> None:
        return await to_thread.run_sync(self._sync_manager.write_to, path, data)

    async def read_from(self, path: str) -> tp.Union[bytes, str]:
        return await to_thread.run_sync(self._sync_manager.read_from, path)

    async def remove_expired(self, ttl: int) -> None:
        return await to_thread.run_sync(self._sync_manager.remove_expired, ttl)
