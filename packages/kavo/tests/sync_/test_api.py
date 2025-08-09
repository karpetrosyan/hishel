import datetime as dt
import uuid
from textwrap import dedent

import pytest
import time_machine
from kavo.client import KavoClient
from kavo.config import Config
from kavo.utils import iterable_to_iterable

from .conftest import EnvPrinter


def test_basic(
    client: KavoClient,
    env_printer: EnvPrinter,
) -> None:
    client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=uuid.UUID(int=0),
    )

    client.put_response_stream(
        request_id=uuid.UUID(int=0),
        stream=iterable_to_iterable([b"chunk1", b"chunk2", b"chunk3"]),
    )

    cache_entry = client.get_cache_entry(key="test_key", options={})
    assert cache_entry is not None
    assert (
        env_printer.get_state()
        == dedent("""
    DB: responses
      - 00000000000000000000000000000000
    DB: responses_chunk
      - 00000000000000000000000000000000:chunk_0
      - 00000000000000000000000000000000:chunk_1
      - 00000000000000000000000000000000:chunk_2
      - 00000000000000000000000000000000:chunk_3
      - 00000000000000000000000000000000:complete
    DB: entries
      - test_key
    """).lstrip()
    )

    assert len(cache_entry["responses"]) == 1


def test_response_stream(
    client: KavoClient,
    env_printer: EnvPrinter,
) -> None:
    client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=uuid.UUID(int=0),
    )

    client.put_response_stream(
        request_id=uuid.UUID(int=0),
        stream=iterable_to_iterable([b"chunk1", b"chunk2", b"chunk3"]),
    )

    assert [chunk for chunk in client.get_response_stream(request_id=uuid.UUID(int=0))] == [
        b"chunk1",
        b"chunk2",
        b"chunk3",
    ]


def test_incomplete_responses(
    client: KavoClient,
    env_printer: EnvPrinter,
) -> None:
    client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=uuid.UUID(int=0),
    )

    cache_entry = client.get_cache_entry("test_key", {})

    assert cache_entry is not None

    assert cache_entry["responses"] == []

    cache_entry = client.get_cache_entry(
        "test_key",
        {
            "allow_incomplete": True,
        },
    )
    assert cache_entry is not None
    assert cache_entry["responses"] == [
        uuid.UUID(int=0),
    ]

    assert (
        env_printer.get_state()
        == dedent("""
    DB: responses
      - 00000000000000000000000000000000
    DB: entries
      - test_key
    """).lstrip()
    )


@pytest.mark.xfail(reason="Something strange is happening with the time machine, unix timestamp does not match")
@time_machine.travel(dt.datetime(2003, 8, 25))  # Author's birthday
def test_soft_delete_response(client: KavoClient, env_printer: EnvPrinter) -> None:
    request_id = uuid.UUID(int=0)
    client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=request_id,
    )

    client.delete_response(id=request_id)

    assert (
        env_printer.get_state()
        == dedent(
            """
    DB: responses
      - 00000000000000000000000000000000 (soft deleted) 2003-08-25 05:00:00
    DB: entries
      - test_key
    """
        ).lstrip()
    )

    cache_entry = client.get_cache_entry(key="test_key", options={})
    assert cache_entry is not None
    assert len(cache_entry["responses"]) == 0


@time_machine.travel(dt.datetime(2003, 8, 25))  # Author's birthday
def test_hard_delete_response(client: KavoClient, env_printer: EnvPrinter) -> None:
    request_id = uuid.UUID(int=0)
    client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=request_id,
    )

    client.delete_response(id=request_id)

    with time_machine.travel(dt.datetime(2003, 8, 25) + dt.timedelta(hours=10)):
        client.put_response(
            key="test_key",
            response={
                "status": 200,
            },
            request_id=uuid.UUID(int=1),
        )
        client.put_response_stream(
            request_id=uuid.UUID(int=1),
            stream=iterable_to_iterable([b"chunk1", b"chunk2", b"chunk3"]),
        )

        assert (
            env_printer.get_state()
            == dedent(
                """
            DB: responses
              - 00000000000000000000000000000001
            DB: responses_chunk
              - 00000000000000000000000000000001:chunk_0
              - 00000000000000000000000000000001:chunk_1
              - 00000000000000000000000000000001:chunk_2
              - 00000000000000000000000000000001:chunk_3
              - 00000000000000000000000000000001:complete
            DB: entries
              - test_key
            """
            ).lstrip()
        )

        cache_entry = client.get_cache_entry(key="test_key", options={})
        assert cache_entry is not None
        assert len(cache_entry["responses"]) == 1


def test_multiple_responses(client: KavoClient, env_printer: EnvPrinter) -> None:
    request_id1 = uuid.UUID(int=1)
    request_id2 = uuid.UUID(int=2)

    client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=request_id1,
    )
    client.put_response_stream(
        request_id=request_id1,
        stream=iterable_to_iterable([b"chunk1", b"chunk2", b"chunk3"]),
    )
    client.put_response(
        key="test_key",
        response={
            "status": 404,
        },
        request_id=request_id2,
    )
    client.put_response_stream(
        request_id=request_id2,
        stream=iterable_to_iterable([b"chunk4", b"chunk5", b"chunk6"]),
    )

    cache_entry = client.get_cache_entry(key="test_key", options={})

    assert cache_entry is not None
    assert cache_entry["key"] == "test_key"
    assert len(cache_entry["responses"]) == 2
    assert set(cache_entry["responses"]) == {request_id1, request_id2}

    assert (
        env_printer.get_state()
        == dedent("""
    DB: responses
      - 00000000000000000000000000000001
      - 00000000000000000000000000000002
    DB: responses_chunk
      - 00000000000000000000000000000001:chunk_0
      - 00000000000000000000000000000001:chunk_1
      - 00000000000000000000000000000001:chunk_2
      - 00000000000000000000000000000001:chunk_3
      - 00000000000000000000000000000001:complete
      - 00000000000000000000000000000002:chunk_0
      - 00000000000000000000000000000002:chunk_1
      - 00000000000000000000000000000002:chunk_2
      - 00000000000000000000000000000002:chunk_3
      - 00000000000000000000000000000002:complete
    DB: entries
      - test_key
""").lstrip()
    )


def test_with_response_stream(client: KavoClient, env_printer: EnvPrinter) -> None:
    request_id = uuid.UUID(int=3)

    client.put_response(
        key="test_key",
        response={
            "status": 200,
            "body": "This is a streamed response",
        },
        request_id=request_id,
    )

    client.put_response_stream(
        request_id=request_id,
        stream=iterable_to_iterable([b"chunk1", b"chunk2", b"chunk3"]),
    )

    assert (
        env_printer.get_state()
        == dedent("""
    DB: responses
      - 00000000000000000000000000000003
    DB: responses_chunk
      - 00000000000000000000000000000003:chunk_0
      - 00000000000000000000000000000003:chunk_1
      - 00000000000000000000000000000003:chunk_2
      - 00000000000000000000000000000003:chunk_3
      - 00000000000000000000000000000003:complete
    DB: entries
      - test_key
    """).lstrip()
    )


def test_with_stampede(client: KavoClient, env_printer: EnvPrinter) -> None:
    request_id = uuid.UUID(int=0)

    with client.stampede_lock("test_key") as (
        acquired,
        stampede_info,
    ):
        assert acquired is True
        assert stampede_info is not None

        client.put_response(
            key="test_key",
            response={
                "status": 200,
            },
            request_id=request_id,
        )

        assert (
            env_printer.get_state()
            == dedent("""
            DB: stampede
              - test_key
            DB: responses
              - 00000000000000000000000000000000
            DB: entries
              - test_key
        """).lstrip()
        )
    assert (
        env_printer.get_state()
        == dedent("""
            DB: responses
              - 00000000000000000000000000000000
            DB: entries
              - test_key
        """).lstrip()
    )


@pytest.mark.parametrize(
    "config",
    [
        Config(
            max_stampede_wait_time=1,
        )
    ],
)
def test_with_long_running_stampede(client: KavoClient, env_printer: EnvPrinter, config: Config) -> None:
    request_id = uuid.UUID(int=0)

    with client.stampede_lock(
        "test_key",
    ) as (
        acquired,
        stampede_info,
    ):
        assert acquired is True
        assert stampede_info is not None

        client.put_response(
            key="test_key",
            response={
                "status": 200,
            },
            request_id=request_id,
        )

        with client.stampede_lock("test_key") as (
            acquired2,
            stampede_info2,
        ):
            assert acquired2 is False
            assert stampede_info2 is not None
            assert stampede_info["lock_id"] == stampede_info2["lock_id"]

        assert (
            env_printer.get_state()
            == dedent("""
            DB: stampede
              - test_key
            DB: responses
              - 00000000000000000000000000000000
            DB: entries
              - test_key
        """).lstrip()
        )


@time_machine.travel(dt.datetime(2003, 8, 25))  # Author's birthday
def test_last_used_time(client: KavoClient, env_printer: EnvPrinter, config: Config) -> None:
    client.put_response("test_key", {"status": 200}, request_id=uuid.UUID(int=0))

    client.update_response_time_to_stale(uuid.UUID(int=0))

    assert (
        env_printer.get_state()
        == dedent("""
            DB: responses
              - 00000000000000000000000000000000
            DB: entries
              - test_key
            DB: staleness_tracker_db
              - 1061773200 -> 00000000000000000000000000000000
        """).lstrip()
    )
    client.put_response("test_key", {"status": 200}, request_id=uuid.UUID(int=1))

    client.update_response_time_to_stale(uuid.UUID(int=1))

    assert (
        env_printer.get_state()
        == dedent("""
            DB: responses
              - 00000000000000000000000000000000
              - 00000000000000000000000000000001
            DB: entries
              - test_key
            DB: staleness_tracker_db
              - 1061773200 -> 00000000000000000000000000000000
              - 1061773200 -> 00000000000000000000000000000001
        """).lstrip()
    )

    with time_machine.travel(dt.datetime(2003, 8, 25) + dt.timedelta(hours=2)):
        client.update_response_time_to_stale(
            uuid.UUID(int=0),
        )

        assert (
            env_printer.get_state()
            == dedent("""
                DB: responses
                  - 00000000000000000000000000000000
                  - 00000000000000000000000000000001
                DB: entries
                  - test_key
                DB: staleness_tracker_db
                  - 1061773200 -> 00000000000000000000000000000001
                  - 1061780400 -> 00000000000000000000000000000000
            """).lstrip()
        )


@time_machine.travel(dt.datetime(2003, 8, 25))  # Author's birthday
def test_last_used_time_with_no_refresh(client: KavoClient, env_printer: EnvPrinter, config: Config) -> None:
    client.put_response(
        "test_key",
        {"status": 200},
        request_id=uuid.UUID(int=0),
        response_options={"no_refresh_on_access": True},
    )

    client.update_response_time_to_stale(uuid.UUID(int=0))

    assert (
        env_printer.get_state()
        == dedent("""
            DB: responses
              - 00000000000000000000000000000000
            DB: entries
              - test_key
            DB: staleness_tracker_db
              - 1061773200 -> 00000000000000000000000000000000
        """).lstrip()
    )

    with time_machine.travel(dt.datetime(2003, 8, 25) + dt.timedelta(hours=2)):
        client.update_response_time_to_stale(
            uuid.UUID(int=0),
        )

        assert (
            env_printer.get_state()
            == dedent("""
            DB: responses
              - 00000000000000000000000000000000
            DB: entries
              - test_key
            DB: staleness_tracker_db
              - 1061773200 -> 00000000000000000000000000000000
        """).lstrip()
        )


@pytest.mark.xfail(reason="Something strange is happening with the time machine, unix timestamp does not match")
@time_machine.travel(dt.datetime(2003, 8, 25))
def test_last_used_time_with_stale_response(client: KavoClient, env_printer: EnvPrinter, config: Config) -> None:
    client.put_response(
        "test_key",
        {"status": 200},
        request_id=uuid.UUID(int=0),
        response_options={"no_refresh_on_access": True},
    )

    client.update_response_time_to_stale(uuid.UUID(int=0))

    assert (
        env_printer.get_state()
        == dedent("""
            DB: responses
              - 00000000000000000000000000000000
            DB: entries
              - test_key
            DB: staleness_tracker_db
              - 1061773200 -> 00000000000000000000000000000000
        """).lstrip()
    )

    with time_machine.travel(dt.datetime(2003, 8, 25) + dt.timedelta(days=365)):
        client.put_response("test_key", {"status": 200}, request_id=uuid.UUID(int=1))

        assert (
            env_printer.get_state()
            == dedent("""
            DB: responses
              - 00000000000000000000000000000000 (soft deleted) 2004-08-24 05:00:00
              - 00000000000000000000000000000001
            DB: entries
              - test_key
            DB: staleness_tracker_db
              - 1061773200 -> 00000000000000000000000000000000
        """).lstrip()
        )
