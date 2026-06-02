from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.core.response import success_response
from apps.users.selectors.library.rating_detail_selector import UserSubjectRatingDetailSelector
from apps.users.services.library.rating_detail_service import (
    UserSubjectRatingDetailService,
)
from apps.users.api.serializers.library.rating_detail_serializer import (
    UserSubjectRatingDetailReplaceRequestSerializer,
    UserSubjectRatingDetailResponseSerializer,
)


class MyUserSubjectRatingDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, user_subject_id: int):
        qs = UserSubjectRatingDetailSelector.list_rating_details(
            user=request.user,
            user_subject_id=user_subject_id,
        )

        serializer = UserSubjectRatingDetailResponseSerializer(
            qs,
            many=True,
        )

        return success_response(data=serializer.data)

    def put(self, request, user_subject_id: int):
        serializer = UserSubjectRatingDetailReplaceRequestSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        qs = UserSubjectRatingDetailService.replace_rating_details(
            user=request.user,
            user_subject_id=user_subject_id,
            details=serializer.validated_data["details"],
        )

        output_serializer = UserSubjectRatingDetailResponseSerializer(
            qs,
            many=True,
        )

        return success_response(data=output_serializer.data)


class MySubjectRatingDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, subject_id):
        qs = UserSubjectRatingDetailSelector.list_rating_details_by_subject_id(
            user=request.user,
            subject_id=subject_id,
        )

        serializer = UserSubjectRatingDetailResponseSerializer(
            qs,
            many=True,
        )

        return success_response(data=serializer.data)

    def put(self, request, subject_id):
        serializer = UserSubjectRatingDetailReplaceRequestSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        qs = UserSubjectRatingDetailService.replace_rating_details_by_subject_id(
            user=request.user,
            subject_id=subject_id,
            details=serializer.validated_data["details"],
        )

        output_serializer = UserSubjectRatingDetailResponseSerializer(
            qs,
            many=True,
        )

        return success_response(data=output_serializer.data)
