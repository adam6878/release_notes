

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus

import requests

# 127.0.0.1, not localhost: on Windows localhost tries IPv6 first and each request waits ~2 s.
URL = "http://127.0.0.1:8080/api/version"
NUM_OF_WORKERS = 20  # threads, not processes, so a slow request doesn't block the next one
DURATION_IN_SECONDS = 120


def request_version() -> str | None:
    """Return the version that answered, or None if the request failed."""
    try:
        response = requests.get(URL, timeout=2)
    except requests.RequestException:
        return None
    if response.status_code != HTTPStatus.OK:
        return None
    version: str = response.json()["version"]
    return version


def send_traffic() -> list[str | None]:
    with ThreadPoolExecutor(max_workers=NUM_OF_WORKERS) as pool:
        futures = []
        end = time.monotonic() + DURATION_IN_SECONDS
        while time.monotonic() < end:
            futures.append(pool.submit(request_version))
            time.sleep(0.1)
        return [future.result() for future in futures]


def main():
    results = send_traffic()
    failed = results.count(None)
    # Counter keeps the order versions were first seen, so the old version prints first.
    for version, count in Counter(result for result in results if result).items():
        print(f"{version}: {count} succeeded")
    print(f"sent: {len(results)}  succeeded: {len(results) - failed}  failed: {failed}")


if __name__ == "__main__":
    main()
