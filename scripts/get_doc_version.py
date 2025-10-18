#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "hishel",
# ]
#
# [tool.uv.sources]
# hishel = { path = "../", editable = true }
# ///

from importlib.metadata import version


def get_doc_version() -> str:
    ver = version("hishel")
    splited = ver.split(".")
    return f"{splited[0]}.{splited[1]}"


if __name__ == "__main__":
    print(get_doc_version())
