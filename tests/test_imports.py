import subprocess
import sys
import textwrap

import pytest

# Some Python builds ship without a usable sqlite3, e.g. runtimes where
# libsqlite3.so is missing, so `import sqlite3` raises ImportError (#502).
# Setting `sys.modules["_sqlite3"] = None` makes the C extension import fail
# the same way. It runs in a subprocess so that the modules already imported
# by this test session are not affected.
IMPORT_WITHOUT_SQLITE3 = """
import sys

sys.modules["_sqlite3"] = None

try:
    import sqlite3
except ImportError:
    pass
else:
    raise AssertionError("sqlite3 should not be importable")

{imports}
"""


@pytest.mark.parametrize(
    "imports",
    [
        "from hishel import AsyncSqliteStorage, SqliteStorage",
        "from hishel.httpx import AsyncCacheClient, CacheClient",
        "from hishel.httpx2 import AsyncCacheClient, CacheClient",
        "from hishel.asgi import ASGICacheMiddleware",
    ],
)
def test_import_without_sqlite3(imports: str) -> None:
    code = textwrap.dedent(IMPORT_WITHOUT_SQLITE3).format(imports=imports)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
