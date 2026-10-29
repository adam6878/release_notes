"""Load test: send steady traffic to the app for a fixed time, then report how many requests
were sent, succeeded (per app version) and failed. Run it during a rollout or rollback to check for downtime.

Usage: python scripts/load_test.py
Exits with code 1 if any request failed.
"""

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus

import requests

# 127.0.0.1, not localhost: on Windows localhost tries IPv6 first and each request waits ~2 s.
URL = "http://127.0.0.1:8080/api/version"
DURATION_IN_SECONDS = 120


def request_version() -> str | None:
    """Return the version that answered, or None if the request failed."""
    try:
        # No Session: each call opens its own connection, so every request is load-balanced on its own.
        response = requests.get(URL, timeout=2)
    except requests.RequestException:  # connection refused/reset, timeout
        return None
    if response.status_code != HTTPStatus.OK:
        return None
    version: str = response.json()["version"]
    return version


def send_traffic() -> list[str | None]:
    """Start a request every 0.1 s for DURATION_IN_SECONDS, each in a thread, without waiting for
    the answer, so a slow response never pauses the traffic. Returns one version (or None) per request."""
    # 20 threads = 10 requests/s x 2 s timeout, so a new request never waits for a free thread.
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = []
        end = time.monotonic() + DURATION_IN_SECONDS
        while time.monotonic() < end:
            futures.append(pool.submit(request_version))
            time.sleep(0.1)
        return [future.result() for future in futures]


def main() -> int:
    results = send_traffic()
    failed = results.count(None)
    # Counter keeps the order versions were first seen, so the old version prints first.
    for version, count in Counter(result for result in results if result).items():
        print(f"{version}: {count} succeeded")
    print(f"sent: {len(results)}  succeeded: {len(results) - failed}  failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
