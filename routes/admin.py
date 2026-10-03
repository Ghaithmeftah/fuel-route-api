from django.contrib import admin

from .models import City, FuelStation


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'state', 'lat', 'lng')
    list_filter = ('state',)
    search_fields = ('name',)


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'address', 'price')
    list_filter = ('city__state',)
    search_fields = ('name', 'city__name')
    list_select_related = ('city',)
