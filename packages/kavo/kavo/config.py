import os
from typing import TypedDict


class Config(TypedDict, total=False):
    # seconds, how long we keep soft deleted responses
    # override default value with the environment variable KAVO_HARD_DELETE_AFTER
    hard_delete_after: int
    """
    How long we keep soft deleted responses (in seconds).
    """

    # seconds, after which interval response should be considered stale if not used
    stale_after: int
    """
    After which interval response should be considered stale if not used (in seconds).
    """

    # seconds, how long we wait for a lock to be stale
    # override default value with the environment variable KAVO_MAX_STAMPEDE_WAIT_TIME
    max_stampede_wait_time: float
    """
    How long we wait for a lock to be stale (in seconds).
    """

    # request db name
    # override default value with the environment variable KAVO_REQUESTS_DB
    requests_db: str
    """
    The name of the database where requests are stored.
    """

    # response db name
    # override default value with the environment variable KAVO_RESPONSES_DB
    responses_db: str
    """
    The name of the database where responses are stored.
    """

    # response timeout in seconds
    # override default value with the environment variable KAVO_RESPONSE_TIMEOUT
    response_timeout: int
    """
    The timeout for responses in seconds.
    """

    # entries db name
    # override default value with the environment variable KAVO_ENTRIES_DB
    entries_db: str
    """
    The name of the database where cache entries are stored.
    """

    # requests chunk db name
    # override default value with the environment variable KAVO_REQUESTS_CHUNK_DB
    requests_chunk_db: str
    """
    The name of the database where request chunks are stored.
    """

    # responses chunk db name
    # override default value with the environment variable KAVO_RESPONSES_CHUNK_DB
    responses_chunk_db: str
    """
    The name of the database where response chunks are stored.
    """

    # stampede db name
    # override default value with the environment variable KAVO_STAMPEDE_DB
    stampede_db: str
    """
    The name of the database where stampede information is stored.
    """

    # response last used db name
    # override default value with the environment variable KAVO_STALENESS_TRACKER_DB
    staleness_tracker_db: str
    """
    The name of the database where response last used information is stored.
    """

    # lmdb path
    # override default value with the environment variable KAVO_LMDB_PATH
    lmdb_path: str
    """
    The path to the LMDB database.
    """


def get_default_config() -> Config:
    """Get the default configuration for Kavo."""

    HARD_DELETE_AFTER = int(os.getenv("KAVO_HARD_DELETE_AFTER", "3600"))  # 1 hour
    STALE_AFTER = int(os.getenv("KAVO_STALE_AFTER", "3600"))  # 1 hour
    MAX_STAMPEDE_WAIT_TIME = int(os.getenv("KAVO_MAX_STAMPEDE_WAIT_TIME", "5"))  # seconds
    REQUESTS_DB = os.getenv("KAVO_REQUESTS_DB", "requests")
    RESPONSES_DB = os.getenv("KAVO_RESPONSES_DB", "responses")
    ENTRIES_DB = os.getenv("KAVO_ENTRIES_DB", "entries")
    REQUESTS_CHUNK_DB = os.getenv("KAVO_REQUESTS_CHUNK_DB", "requests_chunk")
    RESPONSES_CHUNK_DB = os.getenv("KAVO_RESPONSES_CHUNK_DB", "responses_chunk")
    STAMPEDE_DB = os.getenv("KAVO_STAMPEDE_DB", "stampede")
    STALENESS_TRACKER_DB = os.getenv("KAVO_STALENESS_TRACKER_DB", "staleness_tracker_db")
    LMDB_PATH = os.getenv("KAVO_LMDB_PATH", "kavo")

    return {
        "hard_delete_after": HARD_DELETE_AFTER,
        "stale_after": STALE_AFTER,
        "max_stampede_wait_time": MAX_STAMPEDE_WAIT_TIME,
        "requests_db": REQUESTS_DB,
        "responses_db": RESPONSES_DB,
        "entries_db": ENTRIES_DB,
        "requests_chunk_db": REQUESTS_CHUNK_DB,
        "responses_chunk_db": RESPONSES_CHUNK_DB,
        "stampede_db": STAMPEDE_DB,
        "staleness_tracker_db": STALENESS_TRACKER_DB,
        "lmdb_path": LMDB_PATH,
    }
