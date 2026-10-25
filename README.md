# astrotune-stations

The station list used by the AstrotuneRadio Android app. The app downloads `stations.json`
from this repository (through the jsDelivr CDN) about twice a day, so stations can be added
or fixed without releasing a new app version.

Don't edit `stations.json` by hand. It is generated and published from the app project
with `tools/stations/convert_stations.py` and `tools/stations/publish_stations.py`.

The app ignores a published list with fewer than 500 stations, so a broken file can't
empty the app.
