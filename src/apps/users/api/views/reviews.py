from django.db.models import Count, Exists, OuterRef, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.models import CommunityBookmark, CommunityReaction, UserBlock
from apps.index.models import Entity
from apps.index.selectors.projections import entity_summary
from apps.index.services import entity_resolution_service
from apps.users.api.serializers.contracts import ReviewSerializer
from apps.users.api.serializers.reviews import (
    ReviewCreateRequestSerializer,
    ReviewListRequestSerializer,
    ReviewUpdateRequestSerializer,
)
from apps.users.models import Review
from apps.users.services.library.review_service import ReviewService
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


def review_queryset(*, viewer=None):
    queryset = Review.objects.select_related(
        "user_subject",
        "user_subject__entity",
        "user_subject__entity__work",
        "user_subject__user",
        "user_subject__user__profile",
    ).prefetch_related(
        "user_subject__entity__names",
        "user_subject__entity__media__asset",
        "user_subject__entity__index_memberships__collection",
    )
    queryset = queryset.annotate(
        reaction_count=Count(
            "community_reactions",
            filter=Q(
                community_reactions__reaction_type=CommunityReaction.ReactionType.LIKE
            ),
            distinct=True,
        )
    )
    if viewer and viewer.is_authenticated:
        queryset = queryset.annotate(
            viewer_has_liked=Exists(
                CommunityReaction.objects.filter(
                    user=viewer,
                    review_id=OuterRef("pk"),
                    reaction_type=CommunityReaction.ReactionType.LIKE,
                )
            ),
            viewer_has_bookmarked=Exists(
                CommunityBookmark.objects.filter(
                    user=viewer,
                    review_id=OuterRef("pk"),
                )
            ),
        )
    return queryset


def review_data(review: Review) -> dict:
    profile = getattr(review.user_subject.user, "profile", None)
    return {
        "id": review.id,
        "title": review.title,
        "content": review.content,
        "is_public": review.is_public,
        "is_spoiler": review.is_spoiler,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
        "reaction_count": review.reaction_count,
        "entity": entity_summary(review.user_subject.entity, safe=True),
        "library_entry_id": review.user_subject_id,
        "user": {
            "id": review.user_subject.user_id,
            "nickname": profile.nickname if profile else "",
            "avatar": profile.avatar if profile else "",
        },
        "viewer_state": {
            "has_liked": bool(getattr(review, "viewer_has_liked", False)),
            "has_bookmarked": bool(getattr(review, "viewer_has_bookmarked", False)),
        },
    }


def get_my_review(*, user, review_id: int) -> Review:
    try:
        return review_queryset(viewer=user).get(
            pk=review_id,
            user_subject__user=user,
            user_subject__entity__isnull=False,
        )
    except Review.DoesNotExist as exc:
        raise NotFound("Review not found.") from exc


@extend_schema_view(
    get=extend_schema(
        parameters=[ReviewListRequestSerializer, PaginationQuerySerializer],
        responses=api_responses(
            {200: paginated_response("PaginatedReview", ReviewSerializer)}
        ),
    )
)
class MyReviewListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ReviewListRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data
        queryset = review_queryset(viewer=request.user).filter(
            user_subject__user=request.user,
            user_subject__entity__isnull=False,
        )
        if keyword := query.get("keyword", "").strip():
            queryset = queryset.filter(
                Q(title__icontains=keyword) | Q(content__icontains=keyword)
            )
        queryset = queryset.order_by(query["ordering"], "-id")
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([review_data(item) for item in page])


@extend_schema_view(
    get=extend_schema(responses=api_responses({200: ReviewSerializer(many=True)})),
    post=extend_schema(
        request=ReviewCreateRequestSerializer,
        responses=api_responses({201: ReviewSerializer}),
    ),
)
class LibraryEntryReviewListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entry_id: int):
        queryset = (
            review_queryset(viewer=request.user)
            .filter(
                user_subject_id=entry_id,
                user_subject__user=request.user,
                user_subject__entity__isnull=False,
            )
            .order_by("-created_at", "-id")
        )
        return Response([review_data(review) for review in queryset])

    def post(self, request, entry_id: int):
        serializer = ReviewCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = ReviewService.create_review(
            user=request.user,
            user_subject_id=entry_id,
            **serializer.validated_data,
        )
        review = get_my_review(user=request.user, review_id=review.id)
        return Response(review_data(review), status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(responses=api_responses({200: ReviewSerializer})),
    patch=extend_schema(
        request=ReviewUpdateRequestSerializer,
        responses=api_responses({200: ReviewSerializer}),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class MyReviewDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, review_id: int):
        return Response(
            review_data(get_my_review(user=request.user, review_id=review_id))
        )

    def patch(self, request, review_id: int):
        serializer = ReviewUpdateRequestSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ReviewService.update_review(
            user=request.user,
            review_id=review_id,
            **serializer.validated_data,
        )
        return Response(
            review_data(get_my_review(user=request.user, review_id=review_id))
        )

    def delete(self, request, review_id: int):
        ReviewService.delete_review(user=request.user, review_id=review_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {200: paginated_response("PaginatedReview", ReviewSerializer)},
            errors=(404,),
        ),
    )
)
class PublicEntityReviewListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, entity_id):
        try:
            entity = Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist as exc:
            raise NotFound("Entity not found.") from exc
        entity_ids = entity_resolution_service.cluster_ids(entity)
        queryset = review_queryset(viewer=request.user).filter(
            user_subject__entity_id__in=entity_ids,
            user_subject__is_public=True,
            is_public=True,
        )
        if request.user.is_authenticated:
            blocked_users = UserBlock.objects.filter(user=request.user).values(
                "blocked_user_id"
            )
            blocked_by = UserBlock.objects.filter(blocked_user=request.user).values(
                "user_id"
            )
            queryset = queryset.exclude(
                user_subject__user_id__in=blocked_users
            ).exclude(user_subject__user_id__in=blocked_by)
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(
            queryset.order_by("-updated_at", "-id"), request, view=self
        )
        return paginator.get_paginated_response([review_data(item) for item in page])


@extend_schema_view(
    get=extend_schema(responses=api_responses({200: ReviewSerializer}, errors=(404,)))
)
class PublicReviewDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, review_id: int):
        try:
            review = review_queryset(viewer=request.user).get(
                pk=review_id,
                user_subject__entity__isnull=False,
                user_subject__is_public=True,
                is_public=True,
            )
        except Review.DoesNotExist as exc:
            raise NotFound("Review not found.") from exc
        if (
            request.user.is_authenticated
            and UserBlock.objects.filter(
                Q(user=request.user, blocked_user=review.user_subject.user)
                | Q(user=review.user_subject.user, blocked_user=request.user)
            ).exists()
        ):
            raise NotFound("Review not found.")
        return Response(review_data(review))
