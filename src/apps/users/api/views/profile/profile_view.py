from datetime import date, datetime, time

from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.users.api.serializers.profile.profile_serializer import (
    AvatarUploadRequestSerializer,
    ProfileStatsRequestSerializer,
    UserProfileResponseSerializer,
    UserProfileUpdateRequestSerializer,
    UserSettingsUpdateRequestSerializer,
)
from apps.users.selectors.profile import ProfileSelector
from apps.users.services.profile.profile_service import ProfileService
from shared.api.responses import success_response


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
        query_serializer = ProfileStatsRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        year = query_serializer.validated_data["year"]
        user_timezone = query_serializer.validated_data["timezone"]

        start_date = date(year, 1, 1)
        end_date = date(year + 1, 1, 1)
        start_datetime = datetime.combine(start_date, time.min, tzinfo=user_timezone)
        end_datetime = datetime.combine(end_date, time.min, tzinfo=user_timezone)

        data = ProfileSelector.get_stats(
            user=request.user,
            year=year,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            user_timezone=user_timezone,
        )

        return success_response(data=data)
