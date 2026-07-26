from collections import OrderedDict

from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.index.api.serializers.calendar_serializer import (
    CalendarQuerySerializer,
    CalendarSubjectResponseSerializer,
)
from apps.index.selectors.calendar_selector import CalendarSelector
from shared.api.responses import success_response


class CalendarView(APIView):
    permission_classes = [AllowAny]
    WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def get(self, request):
        query_serializer = CalendarQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = CalendarSelector.list_calendar(
            **query_serializer.validated_data,
        )
        serializer = CalendarSubjectResponseSerializer(qs, many=True)

        grouped = OrderedDict()
        weekday_index = {
            weekday: index + 1 for index, weekday in enumerate(self.WEEKDAY_ORDER)
        }
        for item in serializer.data:
            key = item["weekday_en"]
            if key not in grouped:
                grouped[key] = {
                    "weekday": {
                        "id": weekday_index.get(key),
                        "en": key,
                    },
                    "items": [],
                }
            grouped[key]["items"].append(item)

        data = [
            grouped[weekday] for weekday in self.WEEKDAY_ORDER if weekday in grouped
        ]
        return success_response(data=data)
