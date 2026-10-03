from rest_framework import serializers


class RouteQuerySerializer(serializers.Serializer):
    start = serializers.CharField(max_length=120)
    finish = serializers.CharField(max_length=120)

    def validate(self, attrs):
        if attrs['start'].strip().lower() == attrs['finish'].strip().lower():
            raise serializers.ValidationError('Start and finish must be different.')
        return attrs
