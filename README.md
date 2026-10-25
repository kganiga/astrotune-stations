# astrotune-stations

The station list used by the AstrotuneRadio Android app. The app downloads `stations.json`
from this repository (through the jsDelivr CDN) about twice a day, so stations can be added
or fixed without releasing a new app version.

| File | What it is |
|---|---|
| `stations.json` | What the app downloads: the live stations. |
| `stations.all.json` | Every candidate station, including ones whose stream is currently down. |
| `health.json` | How many weekly checks in a row each station's stream has failed. |
| `scripts/refresh_stations.py` | The weekly re-check. |

## Weekly refresh

A GitHub Actions job (`.github/workflows/refresh-stations.yml`) runs every Monday at
06:00 IST. It re-checks every stream in `stations.all.json` and republishes `stations.json`:

- A station is removed after its stream fails **2 weekly checks in a row**, so a short
  outage doesn't remove it.
- A removed station comes back the first week its stream answers again.
- The run stops without changing anything if too few streams answer (for example if the
  runner lost its network), if fewer than 500 stations would remain (the app would reject
  the list), or if more than a quarter of the list would disappear at once. A failed run
  shows up in the Actions tab and GitHub emails you.

To run it now: **Actions** tab → **Refresh station list** → **Run workflow**.

The checks run from GitHub's servers (mostly in the US), so a stream that only works from
India could look dead. The two-strike rule and the limits above keep that from removing
large parts of the list, but watch the run summaries for Indian stations being dropped.

## Changing the station list

Don't edit the JSON files by hand. They're generated from the app project:

```bash
python tools/stations/convert_stations.py
python tools/stations/publish_stations.py <path-to-this-clone>
```

`publish_stations.py` pulls the job's latest commit first, then pushes both lists and asks
jsDelivr to refresh its copy.
