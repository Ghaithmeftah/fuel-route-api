from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteQuerySerializer
from .services.fuel import NoFuelError
from .services.geocoding import LocationError
from .services.routing import RoutingError
from .services.trip import plan_trip

ERROR_STATUS = {
    LocationError: status.HTTP_400_BAD_REQUEST,
    NoFuelError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    RoutingError: status.HTTP_502_BAD_GATEWAY,
}


class RouteView(APIView):
    """
    GET /api/route/?start=Dallas, TX&finish=Chicago, IL
    """

    def get(self, request):
        query = RouteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        start, finish = query.validated_data['start'], query.validated_data['finish']

        try:
            trip = plan_trip(start, finish)
        except (LocationError, NoFuelError, RoutingError) as exc:
            return Response({'detail': str(exc)}, status=ERROR_STATUS[type(exc)])

        map_url = reverse('route-map') + '?' + urlencode({'start': start, 'finish': finish})
        return Response({**trip, 'map_url': request.build_absolute_uri(map_url)})


def route_map(request):
    query = RouteQuerySerializer(data=request.GET)
    if not query.is_valid():
        return render(request, 'routes/map.html', {'error': 'start and finish are required'}, status=400)

    try:
        trip = plan_trip(query.validated_data['start'], query.validated_data['finish'])
    except (LocationError, NoFuelError, RoutingError) as exc:
        return render(request, 'routes/map.html', {'error': str(exc)}, status=ERROR_STATUS[type(exc)])

    return render(request, 'routes/map.html', {'trip': trip})
