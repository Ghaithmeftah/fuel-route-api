# Fuel Route API

Django API that takes a start and finish location in the USA and returns the driving route,
the cheapest places to fuel up along the way and the total fuel cost.

- Vehicle range: 500 miles
- Consumption: 10 miles per gallon
- Fuel prices: `data/fuel_prices.csv`

## Stack

- Django 6.1 + Django REST Framework
- SQLite
- [OSRM](https://project-osrm.org/) public server for routing (free, no API key)
- [Open-Meteo Geocoding](https://open-meteo.com/en/docs/geocoding-api) to locate cities (free, no API key)
- Leaflet + OpenStreetMap tiles for the map page

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
python manage.py migrate
python manage.py load_stations
python manage.py runserver
```

`load_stations` imports the CSV and looks up the coordinates of every city that has a station.
This happens **once**: cities are stored in the database, so running the command again only
geocodes cities that are still missing. The first run takes a while (~3800 cities with the free
API's rate limit).

## API

### `GET /api/route/`

| Param    | Example          | Notes                                   |
|----------|------------------|-----------------------------------------|
| `start`  | `New York, NY`   | `City, ST`, `City, State` or `lat,lng`   |
| `finish` | `Los Angeles, CA`| same                                    |

```
GET /api/route/?start=Dallas, TX&finish=Chicago, IL
```

```json
{
  "start": {"label": "Dallas, TX", "lat": 32.78306, "lng": -96.80667},
  "finish": {"label": "Chicago, IL", "lat": 41.85003, "lng": -87.65005},
  "distance_miles": 966.3,
  "duration_hours": 17.1,
  "total_gallons": 92.49,
  "total_fuel_cost": 263.52,
  "fuel_stops": [
    {
      "name": "CADOO MILLS",
      "address": "I-30/US-67, EXIT 87 & FM-1903",
      "city": "Caddo Mills",
      "state": "TX",
      "price_per_gallon": 2.801,
      "mile": 41.4,
      "gallons": 50.0,
      "cost": 140.05,
      "lat": 33.06567,
      "lng": -96.22776
    }
  ],
  "route": {"type": "LineString", "coordinates": [[-96.806569, 32.783134], "..."]},
  "map_url": "http://127.0.0.1:8000/api/route/map/?start=Dallas%2C+TX&finish=Chicago%2C+IL"
}
```

Errors:

- `400` missing params or location not found / outside the USA
- `422` no fuel station reachable on part of the route
- `502` routing service unavailable

### `GET /api/route/map/`

Same params. Returns an HTML page with the route and the fuel stops drawn on a map.
It reuses the cached result of the API call, so opening it doesn't hit the routing API again.

## How it works

1. **Locations** — `City, ST` is looked up in the database first. Only an unknown city goes to
   the geocoder (and is saved for next time).
2. **Route** — one call to OSRM returns the distance, duration and the full route geometry.
   This is the only external call for a normal request. The geometry is requested as an
   encoded polyline (much lighter than GeoJSON) and thinned to ~1 point per 0.5 mile in the response.
3. **Stations on the route** — stations are kept in memory in a grid (0.5° cells). The route is
   sampled every 2 miles and only nearby cells are checked, so this stays fast even on
   coast-to-coast routes. A station counts as "on the route" if it is within 10 miles of it.
4. **Fuel stops** — greedy strategy for the gas station problem:
   - start at the cheapest station in the first 50 miles (tank starts empty)
   - if a cheaper station is reachable, buy just enough fuel to get there
   - else if the finish is reachable, buy just enough to finish
   - else fill the tank and go to the cheapest station in range
   - a station must be at least $0.10/gal cheaper to be worth an extra stop, which avoids
     stopping for 1-2 gallons to save a cent (NY → LA: 9 stops instead of 18, +$7)
5. **Cache** — the whole result is cached for 24h, repeated requests return instantly.

## Assumptions

- Only US stations are used (Canadian provinces in the CSV are skipped).
- When the same OPIS truck stop appears several times, the lowest price is kept.
- Stations are placed at their city's location (the CSV has no coordinates), which is why the
  "on the route" distance allows 10 miles.
- Total cost = fuel bought at the stops for the trip.

## Tests

```bash
python manage.py test routes
```

A Postman collection is included: `postman_collection.json`.
