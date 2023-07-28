import typing as tp

import httpcore
import httpx


class MockAsyncConnectionPool(httpcore.AsyncConnectionPool):
    async def handle_async_request(
        self, request: httpcore.Request
    ) -> httpcore.Response:
        return self.mocked_responses.pop(0)

    async def add_responses(self, responses: tp.List[httpcore.Response]):
        if not hasattr(self, "mocked_responses"):
            self.mocked_responses = []
        self.mocked_responses.extend(responses)


class MockAsyncTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self.mocked_responses.pop(0)

    async def add_responses(self, responses: tp.List[httpx.Response]):
        if not hasattr(self, "mocked_responses"):
            self.mocked_responses = []
        self.mocked_responses.extend(responses)
