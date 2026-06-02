from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.core.response import success_response
from apps.users.models import UserSubject, Review, Collection
from apps.users.services.profile.profile_service import ProfileService
from apps.users.api.serializers.profile.profile_serializer import (
    AvatarUploadRequestSerializer,
    UserSettingsUpdateRequestSerializer,
    UserProfileResponseSerializer,
    UserProfileUpdateRequestSerializer,
)


class MyProfileView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = ProfileService.get_or_create_profile(user=request.user)

        serializer = UserProfileResponseSerializer(profile)

        return success_response(data=serializer.data)

    def patch(self, request):
        serializer = UserProfileUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = ProfileService.update_profile(
            user=request.user,
            **serializer.validated_data,
        )

        output_serializer = UserProfileResponseSerializer(profile)

        return success_response(data=output_serializer.data)


class MySettingsView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = ProfileService.get_or_create_profile(user=request.user)

        serializer = UserProfileResponseSerializer(profile)

        return success_response(data=serializer.data)

    def patch(self, request):
        serializer = UserSettingsUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = ProfileService.update_profile(
            user=request.user,
            **serializer.validated_data,
        )

        output_serializer = UserProfileResponseSerializer(profile)

        return success_response(data=output_serializer.data)


class MyAvatarUploadView(APIView):

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = AvatarUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        url = ProfileService.upload_avatar(
            user=request.user,
            file_obj=serializer.validated_data["avatar"],
        )

        return success_response(data={"avatar": url})


class MyProfileStatsView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        current_year = timezone.localdate().year
        try:
            year = int(request.query_params.get("year", current_year))
        except (TypeError, ValueError):
            year = current_year

        year = min(max(year, 1970), current_year + 1)
        try:
            user_timezone = ZoneInfo(request.query_params.get("timezone") or "UTC")
        except ZoneInfoNotFoundError:
            user_timezone = ZoneInfo("UTC")

        start_date = date(year, 1, 1)
        end_date = date(year + 1, 1, 1)
        start_datetime = datetime.combine(start_date, time.min, tzinfo=user_timezone)
        end_datetime = datetime.combine(end_date, time.min, tzinfo=user_timezone)

        mark_calendar = list(
            UserSubject.objects.filter(
                user=request.user,
                created_at__gte=start_datetime,
                created_at__lt=end_datetime,
            )
            .annotate(day=TruncDate("created_at", tzinfo=user_timezone))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        available_years = [
            value.year
            for value in UserSubject.objects.filter(user=request.user).datetimes(
                "created_at",
                "year",
                order="DESC",
                tzinfo=user_timezone,
            )
        ]

        data = {
            "year": year,
            "available_years": available_years,
            "totals": {
                "subjects": UserSubject.objects.filter(user=request.user).count(),
                "reviews": Review.objects.filter(user=request.user).count(),
                "collections": Collection.objects.filter(user=request.user).count(),
                "marks_in_year": sum(item["count"] for item in mark_calendar),
            },
            "mark_calendar": [
                {
                    "date": item["day"].isoformat(),
                    "count": item["count"],
                }
                for item in mark_calendar
            ],
        }

        return success_response(data=data)
