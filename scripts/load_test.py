"""Load test: send steady traffic to the app for a fixed time, then report failed requests
and which versions answered. Run it during a rollout or rollback to check for downtime.

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
DURATION = 120  # seconds; longer than a rollout plus the old pods' shutdown

# One answer: (status, version) or, with no response, (None, error name).
Response = tuple[int | None, str | None]


def request_once() -> Response:
    try:
        # No Session: each call opens its own connection, so every request is load-balanced on its own.
        response = requests.get(URL, timeout=2)
    except requests.RequestException as error:  # connection refused/reset, timeout
        return (None, type(error).__name__)
    if response.status_code != HTTPStatus.OK:
        return (response.status_code, None)
    return (HTTPStatus.OK, response.json()["version"])


def send_traffic() -> list[Response]:
    """Start a request every 0.1 s for DURATION seconds, each in a thread, without waiting for
    the answer, so a slow response never pauses the traffic. Returns one (status, detail) per request."""
    # 20 threads = 10 requests/s x 2 s timeout, so a new request never waits for a free thread.
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = []
        end = time.monotonic() + DURATION
        while time.monotonic() < end:
            futures.append(pool.submit(request_once))
            time.sleep(0.1)
        return [future.result() for future in futures]


def print_report(results: list[Response], failures: Counter[Response]) -> None:
    # dict.fromkeys keeps each version once, in the order it was first seen.
    versions = dict.fromkeys(version for status, version in results if status == HTTPStatus.OK)
    print(f"\nrequests: {len(results)}  failed: {sum(failures.values())}")
    print(f"versions seen, in order: {' '.join(versions)}")
    for (status, detail), count in failures.items():
        print(f"  {count} x {status or 'no response'}: {detail}")


def main() -> int:
    results = send_traffic()
    failures = Counter((status, detail) for status, detail in results if status != HTTPStatus.OK)
    print_report(results, failures)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
