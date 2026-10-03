from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from .models import City
from .services.fuel import Candidate, NoFuelError, Station, plan_fuel_stops, stations_along_route
from .services.geocoding import LocationError, resolve_location
from .services.routing import decode_polyline


def make_candidate(mile, price, name=None):
    station = Station(
        id=int(mile * 10), name=name or f'Station {mile}', address='I-40', city='Town',
        state='TX', price=price, lat=0, lng=0,
    )
    return Candidate(mile=mile, station=station)


class PlanFuelStopsTests(SimpleTestCase):

    def plan(self, candidates, total_miles):
        return plan_fuel_stops(candidates, total_miles, tank_range=500, mpg=10)

    def test_short_trip_needs_one_stop(self):
        stops = self.plan([make_candidate(5, 3.0)], total_miles=305)

        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0].gallons, 30)
        self.assertAlmostEqual(stops[0].cost, 90)

    def test_buys_only_enough_to_reach_cheaper_station(self):
        candidates = [make_candidate(0, 4.0), make_candidate(200, 3.0)]
        stops = self.plan(candidates, total_miles=600)

        self.assertEqual([s.mile for s in stops], [0, 200])
        self.assertAlmostEqual(stops[0].gallons, 20)   # 200 miles at the expensive one
        self.assertAlmostEqual(stops[1].gallons, 40)   # rest of the trip at the cheap one

    def test_fills_up_when_current_station_is_cheapest(self):
        candidates = [make_candidate(0, 3.0), make_candidate(300, 4.0), make_candidate(450, 3.5)]
        stops = self.plan(candidates, total_miles=800)

        self.assertAlmostEqual(stops[0].gallons, 50)   # full tank at the cheapest
        self.assertEqual(stops[1].station.price, 3.5)  # then cheapest reachable one
        self.assertAlmostEqual(sum(s.gallons for s in stops), 80)

    def test_no_leg_longer_than_tank_range(self):
        candidates = [make_candidate(m, 3.0 + (m % 7) / 10) for m in range(0, 2400, 90)]
        stops = self.plan(candidates, total_miles=2400)

        legs = [b.mile - a.mile for a, b in zip(stops, stops[1:])]
        self.assertTrue(all(leg <= 500 for leg in legs))
        self.assertAlmostEqual(sum(s.gallons for s in stops), 240)

    def test_skips_stop_for_tiny_saving(self):
        candidates = [make_candidate(0, 3.00), make_candidate(100, 2.98)]
        stops = self.plan(candidates, total_miles=400)

        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0].gallons, 40)

    def test_gap_bigger_than_range_raises(self):
        with self.assertRaises(NoFuelError):
            self.plan([make_candidate(0, 3.0), make_candidate(700, 3.0)], total_miles=1000)

    def test_no_station_near_start_raises(self):
        with self.assertRaises(NoFuelError):
            self.plan([make_candidate(120, 3.0)], total_miles=400)


class StationsAlongRouteTests(SimpleTestCase):

    def test_keeps_only_stations_close_to_the_road(self):
        near = Station(1, 'Near', '', 'A', 'TX', 3.0, lat=32.0, lng=-97.05)
        far = Station(2, 'Far', '', 'B', 'TX', 2.0, lat=33.0, lng=-97.05)
        grid = {(64, -195): [near], (66, -195): [far]}

        route = [[-97.5, 32.0], [-97.0, 32.0], [-96.5, 32.0]]
        found = stations_along_route(route, grid=grid)

        self.assertEqual([c.station.name for c in found], ['Near'])
        self.assertTrue(25 < found[0].mile < 32)


class DecodePolylineTests(SimpleTestCase):

    def test_google_reference_example(self):
        coords = decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@', precision=5)
        self.assertEqual(coords, [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]])


class ResolveLocationTests(TestCase):

    def test_coordinates_are_used_directly(self):
        location = resolve_location('32.7767, -96.7970')
        self.assertEqual((location['lat'], location['lng']), (32.7767, -96.797))

    def test_known_city_does_not_call_geocoder(self):
        City.objects.create(name='Dallas', state='TX', lat=32.77, lng=-96.79)
        with patch('routes.services.geocoding.geocode_city') as geocode:
            location = resolve_location('dallas, texas')

        geocode.assert_not_called()
        self.assertEqual(location['label'], 'Dallas, TX')

    def test_bad_input_raises(self):
        for text in ('Dallas', 'Toronto, ON', '200, 300'):
            with self.subTest(text=text), self.assertRaises(LocationError):
                resolve_location(text)


class RouteApiTests(TestCase):

    def test_missing_params_returns_400(self):
        response = self.client.get('/api/route/')
        self.assertEqual(response.status_code, 400)

    @patch('routes.views.plan_trip', side_effect=LocationError('Could not find "Nowhere, TX"'))
    def test_unknown_location_returns_400(self, _):
        response = self.client.get('/api/route/', {'start': 'Nowhere, TX', 'finish': 'Dallas, TX'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Nowhere', response.json()['detail'])
