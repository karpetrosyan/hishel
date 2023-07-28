import typing as tp

import httpcore
import httpx


class MockConnectionPool(httpcore.ConnectionPool):
    def handle_request(
        self, request: httpcore.Request
    ) -> httpcore.Response:
        return self.mocked_responses.pop(0)

    def add_responses(self, responses: tp.List[httpcore.Response]) -> None:
        if not hasattr(self, "mocked_responses"):
            self.mocked_responses = []
        self.mocked_responses.extend(responses)


class MockTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.mocked_responses.pop(0)

    def add_responses(self, responses: tp.List[httpx.Response]) -> None:
        if not hasattr(self, "mocked_responses"):
            self.mocked_responses = []
        self.mocked_responses.extend(responses)
