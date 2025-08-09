import shutil
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

import lmdb
import msgpack
import pytest
from kavo.client import AsyncKavoClient
from kavo.config import Config, get_default_config

if TYPE_CHECKING:
    from kavo.types_ import Environment

from datetime import datetime

from kavo.labels import get_label


class EnvPrinter:
    def __init__(self, env: "Environment"):
        self.env = env

    def get_state(self) -> str:
        default_config = get_default_config()
        ALL_DBS = [
            db_name
            for db_name in [
                default_config["stampede_db"],
                default_config["responses_db"],
                default_config["responses_chunk_db"],
                default_config["requests_db"],
                default_config["requests_chunk_db"],
                default_config["entries_db"],
                default_config["staleness_tracker_db"],
            ]
        ]

        state: Dict[str, list[str]] = {}
        for db_name in ALL_DBS:
            with self.env.begin(db=self.env.open_db(db_name.encode())) as txn:
                cursor = txn.cursor(db=self.env.open_db(db_name.encode()))
                for key in cursor:
                    if db_name == default_config["responses_db"]:
                        soft_deleted_label = msgpack.unpackb(key[1]).get(get_label("soft_deleted"))
                        state.setdefault(db_name, []).append(
                            uuid.UUID(bytes=key[0]).hex
                            + (
                                f" (soft deleted) {datetime.fromtimestamp(soft_deleted_label)}"
                                if soft_deleted_label
                                else ""
                            )
                        )
                    elif db_name == default_config["entries_db"]:
                        state.setdefault(db_name, []).append(key[0].decode())
                    elif db_name == default_config["stampede_db"]:
                        state.setdefault(db_name, []).append(key[0].decode())
                    elif db_name == default_config["requests_db"]:
                        state.setdefault(db_name, []).append(uuid.UUID(bytes=key[0]).hex)
                    elif (
                        db_name == default_config["requests_chunk_db"]
                        or db_name == default_config["responses_chunk_db"]
                    ):
                        uuid_part = key[0].split(b":")[0]
                        state.setdefault(db_name, []).append(
                            uuid.UUID(bytes=uuid_part).hex + key[0][len(uuid_part) :].decode()
                        )
                    elif db_name == default_config["staleness_tracker_db"]:
                        id_ = key[0]

                        timestamp, response_id = id_[:8], id_[8:]
                        state.setdefault(db_name, []).append(
                            f"{int.from_bytes(timestamp, byteorder='big')} -> {uuid.UUID(bytes=response_id).hex}"
                        )

        pretty_formated = ""

        for db_name, keys in state.items():
            pretty_formated += f"DB: {db_name}\n"
            for k in keys:
                pretty_formated += f"  - {k}\n"
        return pretty_formated


@pytest.fixture(scope="function")
def test_name(request: pytest.FixtureRequest) -> Any:
    """Fixture that returns the name of the current test"""
    return request.node.name


@pytest.fixture
def env(test_name: str) -> "Environment":
    kavo_path = Path(tempfile.gettempdir()) / "kavo"

    shutil.rmtree(kavo_path, ignore_errors=True)
    kavo_path.mkdir(parents=True, exist_ok=True)

    test_env_path = kavo_path / test_name
    return lmdb.open(str(test_env_path), max_dbs=10)


@pytest.fixture
def config() -> Config:
    """Fixture that returns the default configuration for Kavo."""
    return get_default_config()


@pytest.fixture
def client(env: "Environment", config: Config) -> AsyncKavoClient:
    return AsyncKavoClient(env=env, config=config)


@pytest.fixture
def env_printer(env: "Environment") -> EnvPrinter:
    return EnvPrinter(env)
