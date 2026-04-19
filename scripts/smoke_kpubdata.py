from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from kpubdata import Client


def _summarize(label: str, batch: Any) -> None:
    rows = list(getattr(batch, "items", []) or [])
    print(f"\n=== {label} ===")
    print(f"  count: {len(rows)}")
    if rows:
        first = rows[0]
        print(f"  fields: {sorted(first.keys())}")
        print(f"  sample: {json.dumps(first, ensure_ascii=False, default=str)[:500]}")


def _run(label: str, fn: Callable[[], Any]) -> bool:
    try:
        _summarize(label, fn())
        return True
    except Exception as exc:
        print(f"\n=== {label} ===")
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)
        return False


def main() -> int:
    client = Client.from_env()
    results = [
        _run(
            "datago.apt_trade (강남구 2025-03)",
            lambda: client.dataset("datago.apt_trade").list(LAWD_CD="11680", DEAL_YMD="202503"),
        ),
        _run(
            "bok.base_rate (2024-01..2025-12)",
            lambda: client.dataset("bok.base_rate").list(start_date="202401", end_date="202512"),
        ),
        _run(
            "kosis.population_migration (2024-01..2025-12)",
            lambda: client.dataset("kosis.population_migration").list(start_date="202401", end_date="202512"),
        ),
    ]
    print(f"\nsummary: {sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
