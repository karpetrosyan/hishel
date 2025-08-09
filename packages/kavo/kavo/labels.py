# labels could be added to rows so we can filter them later

from typing import Literal

LABEL_PREFIX = "__kavo_label_"


def get_label(
    label: Literal[
        "soft_deleted",
        "created_at",
        # We track delete_at both as a response label and in seperate table
        # so we can index it and find stale responses quickly
        "staleness_tracker",
        "stale_after",
        "no_refresh_on_access",
    ],
) -> str:
    return LABEL_PREFIX + label
