import requests
from django.conf import settings

METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    pass


def decode_polyline(encoded, precision=6):
    coords = []
    index = lat = lng = 0
    factor = 10 ** precision

    while index < len(encoded):
        for axis in ('lat', 'lng'):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 'lat':
                lat += delta
            else:
                lng += delta
        coords.append([lng / factor, lat / factor])

    return coords


def get_route(start, finish):
    points = f"{start['lng']},{start['lat']};{finish['lng']},{finish['lat']}"
    url = f'{settings.OSRM_URL}/{points}'
    params = {'overview': 'full', 'geometries': 'polyline6'}

    try:
        resp = requests.get(url, params=params, timeout=settings.HTTP_TIMEOUT)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError('Routing service is unavailable') from exc

    if data.get('code') != 'Ok' or not data.get('routes'):
        raise RoutingError(data.get('message') or 'No route found between these locations')

    route = data['routes'][0]
    return {
        'distance_miles': route['distance'] / METERS_PER_MILE,
        'duration_hours': route['duration'] / 3600,
        'coordinates': decode_polyline(route['geometry']),
    }
