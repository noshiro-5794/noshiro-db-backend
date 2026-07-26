from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.users.api.serializers.library.review_serializer import (
    ReviewCreateRequestSerializer,
    ReviewDetailResponseSerializer,
    ReviewListRequestSerializer,
    ReviewListResponseSerializer,
    ReviewUpdateRequestSerializer,
)
from apps.users.selectors.library.review_selector import ReviewSelector
from apps.users.services.library.review_service import ReviewService
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


class MyReviewListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = ReviewListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = ReviewSelector.list_my_reviews(
            user=request.user,
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = ReviewListResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


class MyUserSubjectReviewCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, user_subject_id: int):
        serializer = ReviewCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review = ReviewService.create_review(
            user=request.user,
            user_subject_id=user_subject_id,
            **serializer.validated_data,
        )

        output_serializer = ReviewDetailResponseSerializer(review)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


class MySubjectReviewListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, subject_id):
        qs = ReviewSelector.list_my_subject_reviews_by_subject_id(
            user=request.user,
            subject_id=subject_id,
        )

        serializer = ReviewListResponseSerializer(
            qs,
            many=True,
        )

        return success_response(data=serializer.data)

    def post(self, request, subject_id):
        serializer = ReviewCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review = ReviewService.create_review_by_subject_id(
            user=request.user,
            subject_id=subject_id,
            **serializer.validated_data,
        )

        output_serializer = ReviewDetailResponseSerializer(review)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


class MyReviewDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, review_id: int):
        review = ReviewSelector.get_my_review_or_raise(
            user=request.user,
            review_id=review_id,
        )

        serializer = ReviewDetailResponseSerializer(review)

        return success_response(data=serializer.data)

    def patch(self, request, review_id: int):
        serializer = ReviewUpdateRequestSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        review = ReviewService.update_review(
            user=request.user,
            review_id=review_id,
            **serializer.validated_data,
        )

        output_serializer = ReviewDetailResponseSerializer(review)

        return success_response(data=output_serializer.data)

    def delete(self, request, review_id: int):
        ReviewService.delete_review(
            user=request.user,
            review_id=review_id,
        )

        return success_response(
            data=None,
            status_code=status.HTTP_204_NO_CONTENT,
        )


class PublicSubjectReviewListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, subject_id):
        qs = ReviewSelector.list_public_subject_reviews(
            subject_id=subject_id,
            viewer=request.user,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = ReviewListResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


class PublicReviewDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, review_id: int):
        review = ReviewSelector.get_public_review_or_raise(
            review_id=review_id,
            viewer=request.user,
        )

        serializer = ReviewDetailResponseSerializer(review)

        return success_response(data=serializer.data)
