import datetime as dt
import uuid
from datetime import timezone
from textwrap import dedent

import pytest
import time_machine
from kavo.client import AsyncKavoClient
from kavo.config import Config
from kavo.utils import iterable_to_async_iterable

from .conftest import EnvPrinter


@pytest.mark.anyio
async def test_basic(
    client: AsyncKavoClient,
    env_printer: EnvPrinter,
) -> None:
    await client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=uuid.UUID(int=0),
    )

    await client.put_response_stream(
        request_id=uuid.UUID(int=0),
        stream=iterable_to_async_iterable([b"chunk1", b"chunk2", b"chunk3"]),
    )

    cache_entry = await client.get_cache_entry(key="test_key", options={})
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


@pytest.mark.anyio
async def test_response_stream(
    client: AsyncKavoClient,
    env_printer: EnvPrinter,
) -> None:
    await client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=uuid.UUID(int=0),
    )

    await client.put_response_stream(
        request_id=uuid.UUID(int=0),
        stream=iterable_to_async_iterable([b"chunk1", b"chunk2", b"chunk3"]),
    )

    assert [chunk async for chunk in client.get_response_stream(request_id=uuid.UUID(int=0))] == [
        b"chunk1",
        b"chunk2",
        b"chunk3",
    ]


@pytest.mark.anyio
async def test_incomplete_responses(
    client: AsyncKavoClient,
    env_printer: EnvPrinter,
) -> None:
    await client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=uuid.UUID(int=0),
    )

    cache_entry = await client.get_cache_entry("test_key", {})

    assert cache_entry is not None

    assert cache_entry["responses"] == []

    cache_entry = await client.get_cache_entry(
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
@time_machine.travel(dt.datetime(2003, 8, 25, 5))  # Author's birthday
@pytest.mark.anyio
async def test_soft_delete_response(client: AsyncKavoClient, env_printer: EnvPrinter) -> None:
    request_id = uuid.UUID(int=0)
    await client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=request_id,
    )

    await client.delete_response(id=request_id)

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

    cache_entry = await client.get_cache_entry(key="test_key", options={})
    assert cache_entry is not None
    assert len(cache_entry["responses"]) == 0


@time_machine.travel(dt.datetime(2003, 8, 25, 5))  # Author's birthday
@pytest.mark.anyio
async def test_hard_delete_response(client: AsyncKavoClient, env_printer: EnvPrinter) -> None:
    request_id = uuid.UUID(int=0)
    await client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=request_id,
    )

    await client.delete_response(id=request_id)

    with time_machine.travel(dt.datetime(2003, 8, 25) + dt.timedelta(hours=10)):
        await client.put_response(
            key="test_key",
            response={
                "status": 200,
            },
            request_id=uuid.UUID(int=1),
        )
        await client.put_response_stream(
            request_id=uuid.UUID(int=1),
            stream=iterable_to_async_iterable([b"chunk1", b"chunk2", b"chunk3"]),
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

        cache_entry = await client.get_cache_entry(key="test_key", options={})
        assert cache_entry is not None
        assert len(cache_entry["responses"]) == 1


@pytest.mark.anyio
async def test_multiple_responses(client: AsyncKavoClient, env_printer: EnvPrinter) -> None:
    request_id1 = uuid.UUID(int=1)
    request_id2 = uuid.UUID(int=2)

    await client.put_response(
        key="test_key",
        response={
            "status": 200,
        },
        request_id=request_id1,
    )
    await client.put_response_stream(
        request_id=request_id1,
        stream=iterable_to_async_iterable([b"chunk1", b"chunk2", b"chunk3"]),
    )
    await client.put_response(
        key="test_key",
        response={
            "status": 404,
        },
        request_id=request_id2,
    )
    await client.put_response_stream(
        request_id=request_id2,
        stream=iterable_to_async_iterable([b"chunk4", b"chunk5", b"chunk6"]),
    )

    cache_entry = await client.get_cache_entry(key="test_key", options={})

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


@pytest.mark.anyio
async def test_with_response_stream(client: AsyncKavoClient, env_printer: EnvPrinter) -> None:
    request_id = uuid.UUID(int=3)

    await client.put_response(
        key="test_key",
        response={
            "status": 200,
            "body": "This is a streamed response",
        },
        request_id=request_id,
    )

    await client.put_response_stream(
        request_id=request_id,
        stream=iterable_to_async_iterable([b"chunk1", b"chunk2", b"chunk3"]),
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


@pytest.mark.anyio
async def test_with_stampede(client: AsyncKavoClient, env_printer: EnvPrinter) -> None:
    request_id = uuid.UUID(int=0)

    async with client.async_stampede_lock("test_key") as (
        acquired,
        stampede_info,
    ):
        assert acquired is True
        assert stampede_info is not None

        await client.put_response(
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


@pytest.mark.anyio
@pytest.mark.parametrize(
    "config",
    [
        Config(
            max_stampede_wait_time=1,
        )
    ],
)
async def test_with_long_running_stampede(client: AsyncKavoClient, env_printer: EnvPrinter, config: Config) -> None:
    request_id = uuid.UUID(int=0)

    async with client.async_stampede_lock(
        "test_key",
    ) as (
        acquired,
        stampede_info,
    ):
        assert acquired is True
        assert stampede_info is not None

        await client.put_response(
            key="test_key",
            response={
                "status": 200,
            },
            request_id=request_id,
        )

        async with client.async_stampede_lock("test_key") as (
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
@pytest.mark.anyio
async def test_last_used_time(client: AsyncKavoClient, env_printer: EnvPrinter, config: Config) -> None:
    await client.put_response("test_key", {"status": 200}, request_id=uuid.UUID(int=0))

    await client.update_response_time_to_stale(uuid.UUID(int=0))

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
    await client.put_response("test_key", {"status": 200}, request_id=uuid.UUID(int=1))

    await client.update_response_time_to_stale(uuid.UUID(int=1))

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
        await client.update_response_time_to_stale(
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
@pytest.mark.anyio
async def test_last_used_time_with_no_refresh(client: AsyncKavoClient, env_printer: EnvPrinter, config: Config) -> None:
    await client.put_response(
        "test_key",
        {"status": 200},
        request_id=uuid.UUID(int=0),
        response_options={"no_refresh_on_access": True},
    )

    await client.update_response_time_to_stale(uuid.UUID(int=0))

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
        await client.update_response_time_to_stale(
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
@pytest.mark.anyio
async def test_last_used_time_with_stale_response(
    client: AsyncKavoClient, env_printer: EnvPrinter, config: Config
) -> None:
    await client.put_response(
        "test_key",
        {"status": 200},
        request_id=uuid.UUID(int=0),
        response_options={"no_refresh_on_access": True},
    )

    await client.update_response_time_to_stale(uuid.UUID(int=0))

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

    with time_machine.travel(dt.datetime(2003, 8, 25, tzinfo=timezone.utc) + dt.timedelta(days=10)):
        await client.put_response("test_key", {"status": 200}, request_id=uuid.UUID(int=1))

        assert (
            env_printer.get_state()
            == dedent("""
            DB: responses
              - 00000000000000000000000000000000 (soft deleted) 2004-08-24 00:00:00
              - 00000000000000000000000000000001
            DB: entries
              - test_key
            DB: staleness_tracker_db
              - 1061773200 -> 00000000000000000000000000000000
        """).lstrip()
        )
