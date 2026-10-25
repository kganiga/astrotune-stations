"""Weekly refresh: re-probe every stream in stations.all.json and publish the live ones.

    python scripts/refresh_stations.py

stations.all.json  every candidate station, dead streams included (written by the app
                   project's convert_stations.py)
health.json        {station_id: consecutive failed weekly checks}
stations.json      what the app downloads: the master list, in order, minus stations whose
                   stream failed STRIKES checks in a row

One bad check doesn't remove a station (servers have outages, and this runs far from most
listeners), and a removed station comes back the first week its stream answers again.
Exits non-zero without writing anything if the result looks wrong, so a broken run (say the
runner lost its network) can't empty the app.
"""
import concurrent.futures
import http.client
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "stations.all.json")
PUBLISHED = os.path.join(ROOT, "stations.json")
HEALTH = os.path.join(ROOT, "health.json")

STRIKES = 2
MIN_STATIONS = 500          # the app ignores a smaller list (StationListValidator.MIN_STATIONS)
MAX_SHRINK = 0.25           # refuse to drop more than this share of the published list at once
# Many Indian streams refuse or time out from GitHub's (mostly US) runners while working fine
# in India, so this job never removes them; it only brings dead ones back. Indian stations are
# removed by the local check in the app project, which runs from India.
NEVER_REMOVE_COUNTRIES = {"IN"}
UA = "Mozilla/5.0 (Linux; Android 14) AstrotuneRadio/1.0"
SSL_CTX = ssl.create_default_context()


def probe(url, timeout):
    """'ok', 'dead' or 'timeout', from the response status alone (the stream isn't read)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Icy-MetaData": "1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            return "ok" if 200 <= resp.status < 300 else "dead"
    except urllib.error.HTTPError:
        return "dead"
    except http.client.BadStatusLine as e:
        # Shoutcast v1 answers "ICY 200 OK", which http.client can't parse but players accept.
        return "ok" if "ICY 200" in str(e) else "dead"
    except (socket.timeout, TimeoutError):
        return "timeout"
    except urllib.error.URLError as e:
        return "timeout" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "dead"
    except Exception:
        return "dead"


def run_pass(urls, workers, timeout):
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe, url, timeout): sid for sid, url in urls.items()}
        return {futures[f]: f.result() for f in concurrent.futures.as_completed(futures)}


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write(path, data, **kwargs):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, **kwargs)


def main():
    master = load(MASTER, None)
    if not master:
        sys.exit("stations.all.json is missing or empty")
    previous = load(PUBLISHED, [])
    previous_ids = {s["id"] for s in previous}
    health = load(HEALTH, {})

    urls = {s["id"]: s["streamUrl"] for s in master}
    results = run_pass(urls, workers=24, timeout=10)
    retry = {sid: urls[sid] for sid, state in results.items() if state == "timeout"}
    results.update(run_pass(retry, workers=8, timeout=20))
    answered = sum(state == "ok" for state in results.values())
    print(f"probed {len(results)} streams: {answered} answered, {len(retry)} needed a retry")
    # Checked before any strike is recorded: a run that couldn't reach most servers says
    # nothing about the stations.
    if previous and answered < len(previous) * (1 - MAX_SHRINK):
        sys.exit(f"Only {answered} streams answered (last list had {len(previous)}); looks like a network problem")

    new_health = {}
    for station in master:
        sid = station["id"]
        # A station seen for the first time starts from where the last publish left it.
        before = health.get(sid, 0 if sid in previous_ids else STRIKES)
        new_health[sid] = 0 if results[sid] == "ok" else min(before + 1, 99)

    def keep(station):
        sid = station["id"]
        if station.get("countryCode") in NEVER_REMOVE_COUNTRIES and sid in previous_ids:
            return True
        return new_health[sid] < STRIKES

    published = [s for s in master if keep(s)]
    published_ids = {s["id"] for s in published}

    if len(published) < MIN_STATIONS:
        sys.exit(f"Refusing to publish only {len(published)} stations")
    if previous and len(published) < len(previous) * (1 - MAX_SHRINK):
        sys.exit(f"Refusing to shrink the list from {len(previous)} to {len(published)} in one run")

    revived = len(published_ids - previous_ids)
    dropped = len(previous_ids - published_ids)
    print(f"published {len(published)} stations ({revived} back, {dropped} removed)")

    write(PUBLISHED, published, separators=(",", ":"))
    write(HEALTH, new_health, separators=(",", ":"), sort_keys=True)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"Probed {len(results)} streams, {answered} answered.\n\n"
                    f"Published **{len(published)}** stations: {revived} back, {dropped} removed.\n")


if __name__ == "__main__":
    main()
