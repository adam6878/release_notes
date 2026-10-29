"""Send steady traffic while a command (a rollout or rollback) runs, then count failed requests.

Usage: python scripts/rollout_check.py <url> <command...>
Exits with code 1 if any request failed or the command itself failed.
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from subprocess import run

INTERVAL = 0.1  # seconds between requests
BEFORE = 3      # seconds of traffic before the command starts
AFTER = 10      # seconds of traffic after it ends, while the old pods shut down


def send_traffic(url, results, stop):
    """Request the URL until told to stop. Each result is (status, version or error)."""
    while not stop.is_set():
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                results.append((response.status, json.load(response)["version"]))
        except urllib.error.HTTPError as error:  # the server answered with 4xx/5xx
            results.append((error.code, None))
        except (OSError, ValueError) as error:  # connection refused/reset, timeout, bad body
            results.append((None, str(error)))
        time.sleep(INTERVAL)


def main():
    url, command = sys.argv[1], sys.argv[2:]
    results = []
    stop = threading.Event()

    # Traffic runs in a background thread while the main thread runs the command.
    traffic = threading.Thread(target=send_traffic, args=(url, results, stop))
    traffic.start()
    time.sleep(BEFORE)
    command_ok = run(command, check=False).returncode == 0  # a failed command is reported, not raised
    time.sleep(AFTER)
    stop.set()
    traffic.join()

    failed = [(status, detail) for status, detail in results if status != 200]
    # dict.fromkeys keeps the first time each version appeared, in order.
    versions = dict.fromkeys(version for status, version in results if status == 200)

    print(f"\nrequests: {len(results)}  failed: {len(failed)}")
    print(f"versions seen, in order: {' '.join(versions)}")
    for (status, detail), count in Counter(failed).items():
        print(f"  {count} x {status or 'no response'}: {detail or ''}")

    sys.exit(0 if command_ok and not failed else 1)


if __name__ == "__main__":
    main()
