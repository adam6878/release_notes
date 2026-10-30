

import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus

import requests

# The dev cluster. 127.0.0.1, not localhost: on Windows localhost tries IPv6 first and each
# request waits ~2 s.
DEFAULT_TARGET = "127.0.0.1:8080"
NUM_OF_WORKERS = 20
DURATION_IN_SECONDS = 120


def get_version(url: str) -> str | None:
    try:
        response = requests.get(url, timeout=2)
    except requests.RequestException:
        return None
    if response.status_code != HTTPStatus.OK:
        return None
    version: str = response.json()["version"]
    return version


def send_traffic(url: str) -> list[str | None]:
    with ThreadPoolExecutor(max_workers=NUM_OF_WORKERS) as pool:
        futures = []
        end = time.monotonic() + DURATION_IN_SECONDS
        while time.monotonic() < end:
            futures.append(pool.submit(get_version, url))
            time.sleep(0.1)
        return [future.result() for future in futures]


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    results = send_traffic(f"http://{target}/api/version")
    failed = results.count(None)
    # Counter keeps the order versions were first seen, so the old version prints first.
    for version, count in Counter(result for result in results if result).items():
        print(f"{version}: {count} succeeded")
    print(f"sent: {len(results)}  succeeded: {len(results) - failed}  failed: {failed}")


if __name__ == "__main__":
    main()
