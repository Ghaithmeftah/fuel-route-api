from django.db import models


class City(models.Model):
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'cities'
        constraints = [
            models.UniqueConstraint(fields=['name', 'state'], name='unique_city_state'),
        ]

    def __str__(self):
        return f'{self.name}, {self.state}'

    @property
    def is_located(self):
        return self.lat is not None and self.lng is not None


class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='stations')
    rack_id = models.IntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=3)

    def __str__(self):
        return f'{self.name} ({self.city})'
