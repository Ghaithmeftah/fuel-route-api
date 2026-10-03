import re
import time

import requests
from django.conf import settings

from routes.models import City

US_STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'DC': 'District of Columbia',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois',
    'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana',
    'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota',
    'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon',
    'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota',
    'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia',
    'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
}
STATE_CODES = {name.lower(): code for code, name in US_STATES.items()}

COORDS_RE = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$')

_session = requests.Session()


class LocationError(Exception):
    pass


def _simplify(name):
    return re.sub(r'[^a-z]', '', name.lower())


def _name_variants(name):
    variants = [name]
    swaps = [
        (r'^Saint\b', 'St.'), (r'^St\.?\s', 'Saint '),
        (r'^Mount\b', 'Mt.'), (r'^Mt\.?\s', 'Mount '),
        (r'^Fort\b', 'Ft.'), (r'^Ft\.?\s', 'Fort '),
        (r'\bMc\s+', 'Mc'),
    ]
    for pattern, repl in swaps:
        changed = re.sub(pattern, repl, name)
        if changed != name and changed not in variants:
            variants.append(changed)
    return variants


def _search(name):
    params = {'name': name, 'count': 20, 'countryCode': 'US', 'language': 'en'}
    for _ in range(3):
        resp = _session.get(settings.GEOCODER_URL, params=params, timeout=settings.HTTP_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(30)
            continue
        resp.raise_for_status()
        return resp.json().get('results', [])
    return []


def geocode_city(name, state):
    state_name = US_STATES.get(state)
    if not state_name:
        return None

    variants = _name_variants(name)
    wanted = {_simplify(v) for v in variants}
    for variant in variants:
        for result in _search(variant):
            if result.get('admin1') == state_name and _simplify(result['name']) in wanted:
                return result['latitude'], result['longitude']
    return None


def _parse_state(value):
    value = value.strip()
    if value.upper() in US_STATES:
        return value.upper()
    return STATE_CODES.get(value.lower())


def resolve_location(text):
    match = COORDS_RE.match(text)
    if match:
        lat, lng = float(match.group(1)), float(match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise LocationError(f'Invalid coordinates: "{text}"')
        return {'label': f'{lat:.5f}, {lng:.5f}', 'lat': lat, 'lng': lng}

    if ',' not in text:
        raise LocationError(f'Use "City, ST" format, got "{text}"')

    city_name, state_part = (part.strip() for part in text.rsplit(',', 1))
    state = _parse_state(state_part)
    if not city_name or not state:
        raise LocationError(f'"{text}" is not a US location')

    city = City.objects.filter(name__iexact=city_name, state=state, lat__isnull=False).first()
    if city is None:
        try:
            coords = geocode_city(city_name, state)
        except requests.RequestException as exc:
            raise LocationError(f'Geocoding failed for "{text}"') from exc
        if coords is None:
            raise LocationError(f'Could not find "{text}"')
        city, _ = City.objects.update_or_create(
            name=city_name.title(), state=state,
            defaults={'lat': coords[0], 'lng': coords[1]},
        )

    return {'label': str(city), 'lat': city.lat, 'lng': city.lng}
