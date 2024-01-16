import typing as tp
from datetime import datetime, timedelta

from anyio import to_thread


class S3Manager:
    def __init__(self, client: tp.Any, bucket_name: str, is_binary: bool = False):
        self._client = client
        self._bucket_name = bucket_name
        self._is_binary = is_binary

    def write_to(self, path: str, data: tp.Union[bytes, str]) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")

        self._client.put_object(Bucket=self._bucket_name, Key=path, Body=data, Metadata={"hishel": "Is the best"})

    def read_from(self, path: str) -> tp.Union[bytes, str]:
        response = self._client.get_object(
            Bucket=self._bucket_name,
            Key=path,
        )

        if "hishel" not in response["Metadata"]:
            raise RuntimeError("This object is not created by Hishel")

        content = response["Body"].read()

        if self._is_binary:
            return tp.cast(bytes, content)

        return tp.cast(str, content.decode("utf-8"))

    def remove_expired(self, ttl: int) -> None:
        for obj in self._client.list_objects(Bucket=self._bucket_name)["Contents"]:
            if "Hishel" not in obj["Metadata"]:
                continue

            if datetime.now() - obj["LastModified"] > timedelta(milliseconds=ttl):
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
