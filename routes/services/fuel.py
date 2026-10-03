from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from math import floor

from routes.models import FuelStation

from .geo import haversine_miles

GRID_SIZE = 0.5        
SAMPLE_EVERY = 2       
MAX_DETOUR = 10        
START_WINDOW = 50
MIN_SAVING = 0.10


class NoFuelError(Exception):
    pass


@dataclass(frozen=True)
class Station:
    id: int
    name: str
    address: str
    city: str
    state: str
    price: float
    lat: float
    lng: float


@dataclass
class Candidate:
    mile: float
    station: Station


@dataclass
class Stop:
    mile: float
    station: Station
    gallons: float
    cost: float


def _cell(lat, lng):
    return floor(lat / GRID_SIZE), floor(lng / GRID_SIZE)


@cache
def station_grid():
    grid = defaultdict(list)
    qs = FuelStation.objects.select_related('city').filter(city__lat__isnull=False)
    for s in qs:
        station = Station(
            id=s.id, name=s.name, address=s.address, city=s.city.name, state=s.city.state,
            price=float(s.price), lat=s.city.lat, lng=s.city.lng,
        )
        grid[_cell(station.lat, station.lng)].append(station)
    return dict(grid)


def _sample_route(coordinates):
    lng, lat = coordinates[0]
    yield 0.0, lat, lng

    travelled = 0.0
    next_sample = SAMPLE_EVERY
    prev_lat, prev_lng = lat, lng
    for lng, lat in coordinates[1:]:
        travelled += haversine_miles(prev_lat, prev_lng, lat, lng)
        if travelled >= next_sample:
            yield travelled, lat, lng
            next_sample = travelled + SAMPLE_EVERY
        prev_lat, prev_lng = lat, lng

    yield travelled, prev_lat, prev_lng


def stations_along_route(coordinates, grid=None):
    grid = station_grid() if grid is None else grid
    best = {}  # station id -> (distance to road, mile, station)

    for mile, lat, lng in _sample_route(coordinates):
        row, col = _cell(lat, lng)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                for station in grid.get((row + dr, col + dc), ()):
                    dist = haversine_miles(lat, lng, station.lat, station.lng)
                    if dist > MAX_DETOUR:
                        continue
                    seen = best.get(station.id)
                    if seen is None or dist < seen[0]:
                        best[station.id] = (dist, mile, station)

    candidates = [Candidate(mile=mile, station=station) for _, mile, station in best.values()]
    candidates.sort(key=lambda c: (c.mile, c.station.price))
    return candidates


def plan_fuel_stops(candidates, total_miles, tank_range, mpg):
    candidates = [c for c in candidates if c.mile < total_miles]

    near_start = [c for c in candidates if c.mile <= START_WINDOW]
    if not near_start:
        raise NoFuelError(f'No fuel station within {START_WINDOW} miles of the start')
    current = min(near_start, key=lambda c: (c.station.price, c.mile))
    index = candidates.index(current)

    fuel = 0.0  
    stops = []

    while True:
        reach = current.mile + tank_range
        ahead = [c for c in candidates[index + 1:] if current.mile < c.mile <= reach]
        cheaper = next(
            (c for c in ahead if c.station.price <= current.station.price - MIN_SAVING), None
        )

        if cheaper:
            target, next_stop = cheaper.mile - current.mile, cheaper
        elif total_miles <= reach:
            target, next_stop = total_miles - current.mile, None
        elif ahead:
            target = tank_range
            best_price = min(c.station.price for c in ahead)
            next_stop = max(
                (c for c in ahead if c.station.price <= best_price + MIN_SAVING),
                key=lambda c: c.mile,
            )
        else:
            raise NoFuelError(f'No fuel station within range after mile {current.mile:.0f}')

        to_buy = max(target - fuel, 0)
        if to_buy > 0:
            gallons = to_buy / mpg
            stops.append(Stop(
                mile=current.mile, station=current.station,
                gallons=gallons, cost=gallons * current.station.price,
            ))
        fuel += to_buy

        if next_stop is None:
            break

        fuel -= next_stop.mile - current.mile
        current = next_stop
        index = candidates.index(current)

    return stops
