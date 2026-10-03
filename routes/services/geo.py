from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(a))


def thin_line(coordinates, min_gap=0.5):
    kept = [coordinates[0]]
    for lng, lat in coordinates[1:-1]:
        last_lng, last_lat = kept[-1]
        if haversine_miles(last_lat, last_lng, lat, lng) >= min_gap:
            kept.append([round(lng, 5), round(lat, 5)])
    kept.append(coordinates[-1])
    return kept
