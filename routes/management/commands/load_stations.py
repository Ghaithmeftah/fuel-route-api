import csv
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from routes.models import City, FuelStation
from routes.services.geocoding import US_STATES, geocode_city


class Command(BaseCommand):
    help = 'Import fuel prices from the CSV and locate each city (geocoding runs only once per city).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default=str(Path(settings.BASE_DIR) / 'data' / 'fuel_prices.csv'),
            help='Path to the fuel prices CSV',
        )

    def handle(self, *args, **options):
        rows = self.read_csv(options['file'])
        self.stdout.write(f'{len(rows)} US stations found in the CSV')

        cities = self.save_cities(rows)
        self.locate_cities()
        self.save_stations(rows, cities)

        located = FuelStation.objects.filter(city__lat__isnull=False).count()
        missing = City.objects.filter(lat__isnull=True).values_list('name', 'state')
        self.stdout.write(self.style.SUCCESS(
            f'Done: {FuelStation.objects.count()} stations saved, {located} placed on the map'
        ))
        if missing:
            self.stdout.write(self.style.WARNING(
                'Cities not found: ' + ', '.join(f'{n}, {s}' for n, s in missing)
            ))

    def read_csv(self, path):
        stations = {}
        with open(path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                state = row['State'].strip()
                if state not in US_STATES:
                    continue  # Canadian stations, out of scope

                opis_id = int(row['OPIS Truckstop ID'])
                price = Decimal(row['Retail Price']).quantize(Decimal('0.001'))
                if opis_id in stations and stations[opis_id]['price'] <= price:
                    continue

                stations[opis_id] = {
                    'opis_id': opis_id,
                    'name': row['Truckstop Name'].strip(),
                    'address': row['Address'].strip(),
                    'city': row['City'].strip(),
                    'state': state,
                    'rack_id': int(row['Rack ID']) if row['Rack ID'] else None,
                    'price': price,
                }
        return list(stations.values())

    def save_cities(self, rows):
        wanted = {(r['city'], r['state']) for r in rows}
        existing = {(c.name, c.state) for c in City.objects.all()}
        City.objects.bulk_create(City(name=n, state=s) for n, s in wanted - existing)
        return {(c.name, c.state): c for c in City.objects.all()}

    def locate_cities(self):
        pending = list(City.objects.filter(lat__isnull=True))
        if not pending:
            return

        self.stdout.write(f'Geocoding {len(pending)} cities, this runs only once...')
        for i, city in enumerate(pending, start=1):
            coords = geocode_city(city.name, city.state)
            if coords:
                city.lat, city.lng = coords
                city.save(update_fields=['lat', 'lng'])
            if i % 200 == 0:
                self.stdout.write(f'  {i}/{len(pending)}')

    @transaction.atomic
    def save_stations(self, rows, cities):
        FuelStation.objects.all().delete()
        FuelStation.objects.bulk_create(
            FuelStation(
                opis_id=r['opis_id'],
                name=r['name'],
                address=r['address'],
                city=cities[(r['city'], r['state'])],
                rack_id=r['rack_id'],
                price=r['price'],
            )
            for r in rows
        )
