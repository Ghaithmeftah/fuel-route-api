import hashlib

from django.conf import settings
from django.core.cache import cache

from .fuel import plan_fuel_stops, stations_along_route
from .geo import thin_line
from .geocoding import resolve_location
from .routing import get_route


def _cache_key(start, finish):
    raw = f'{start.strip().lower()}|{finish.strip().lower()}'
    return 'trip:' + hashlib.md5(raw.encode()).hexdigest()


def plan_trip(start_text, finish_text):
    key = _cache_key(start_text, finish_text)
    trip = cache.get(key)
    if trip is not None:
        return trip

    start = resolve_location(start_text)
    finish = resolve_location(finish_text)
    route = get_route(start, finish)

    candidates = stations_along_route(route['coordinates'])
    stops = plan_fuel_stops(
        candidates,
        total_miles=route['distance_miles'],
        tank_range=settings.VEHICLE_RANGE_MILES,
        mpg=settings.VEHICLE_MPG,
    )

    trip = {
        'start': start,
        'finish': finish,
        'distance_miles': round(route['distance_miles'], 1),
        'duration_hours': round(route['duration_hours'], 1),
        'total_gallons': round(sum(s.gallons for s in stops), 2),
        'total_fuel_cost': round(sum(s.cost for s in stops), 2),
        'fuel_stops': [
            {
                'name': s.station.name,
                'address': s.station.address,
                'city': s.station.city,
                'state': s.station.state,
                'price_per_gallon': round(s.station.price, 3),
                'mile': round(s.mile, 1),
                'gallons': round(s.gallons, 2),
                'cost': round(s.cost, 2),
                'lat': s.station.lat,
                'lng': s.station.lng,
            }
            for s in stops
        ],
        'route': {
            'type': 'LineString',
            'coordinates': thin_line(route['coordinates']),
        },
    }
    cache.set(key, trip)
    return trip
