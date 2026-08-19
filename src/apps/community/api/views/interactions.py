from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.api.serializers.interactions import (
    CommunityBookmarkListRequestSerializer,
    CommunityBookmarkResponseSerializer,
    CommunityReactionResponseSerializer,
)
from apps.community.models import CommunityBookmark, CommunityReaction
from apps.community.selectors.interaction_selector import CommunityBookmarkSelector
from apps.community.selectors.target_selector import CommunityTargetSelector
from apps.community.services.interaction_service import CommunityInteractionService
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


@extend_schema_view(
    put=extend_schema(
        request=None,
        parameters=[
            OpenApiParameter(
                "target_type",
                OpenApiTypes.STR,
                OpenApiParameter.PATH,
                enum=sorted(CommunityTargetSelector.REACTION_TARGETS),
            ),
            OpenApiParameter(
                "reaction_type",
                OpenApiTypes.STR,
                OpenApiParameter.PATH,
                enum=CommunityReaction.ReactionType.values,
            ),
        ],
        responses=api_responses(
            {
                200: CommunityReactionResponseSerializer,
                201: CommunityReactionResponseSerializer,
            }
        ),
    ),
    delete=extend_schema(
        parameters=[
            OpenApiParameter(
                "target_type",
                OpenApiTypes.STR,
                OpenApiParameter.PATH,
                enum=sorted(CommunityTargetSelector.REACTION_TARGETS),
            ),
            OpenApiParameter(
                "reaction_type",
                OpenApiTypes.STR,
                OpenApiParameter.PATH,
                enum=CommunityReaction.ReactionType.values,
            ),
        ],
        responses=api_responses({204: None}),
    ),
)
class ReactionView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, target_type: str, target_id: int, reaction_type: str):
        if target_type not in CommunityTargetSelector.REACTION_TARGETS:
            raise serializers.ValidationError(
                {"target_type": "Unsupported target type."}
            )
        if reaction_type not in CommunityReaction.ReactionType.values:
            raise serializers.ValidationError(
                {"reaction_type": "Unsupported reaction type."}
            )
        reaction, created = CommunityInteractionService.react(
            user=request.user,
            target_type=target_type,
            target_id=target_id,
            reaction_type=reaction_type,
        )
        return Response(
            CommunityReactionResponseSerializer(reaction).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, target_type: str, target_id: int, reaction_type: str):
        if (
            target_type not in CommunityTargetSelector.REACTION_TARGETS
            or reaction_type not in CommunityReaction.ReactionType.values
        ):
            return Response(status=status.HTTP_204_NO_CONTENT)
        CommunityReaction.objects.filter(
            user=request.user,
            reaction_type=reaction_type,
            **{f"{target_type}_id": target_id},
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(
        parameters=[CommunityBookmarkListRequestSerializer, PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedCommunityBookmark", CommunityBookmarkResponseSerializer
                )
            }
        ),
    )
)
class BookmarkListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CommunityBookmarkListRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = CommunityBookmarkSelector.list_my_bookmarks(
            user=request.user, **serializer.validated_data
        )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            CommunityBookmarkResponseSerializer(page, many=True).data
        )


@extend_schema_view(
    put=extend_schema(
        request=None,
        parameters=[
            OpenApiParameter(
                "target_type",
                OpenApiTypes.STR,
                OpenApiParameter.PATH,
                enum=sorted(CommunityTargetSelector.BOOKMARK_TARGETS),
            )
        ],
        responses=api_responses(
            {
                200: CommunityBookmarkResponseSerializer,
                201: CommunityBookmarkResponseSerializer,
            }
        ),
    ),
    delete=extend_schema(
        parameters=[
            OpenApiParameter(
                "target_type",
                OpenApiTypes.STR,
                OpenApiParameter.PATH,
                enum=sorted(CommunityTargetSelector.BOOKMARK_TARGETS),
            )
        ],
        responses=api_responses({204: None}),
    ),
)
class BookmarkView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, target_type: str, target_id: int):
        if target_type not in CommunityTargetSelector.BOOKMARK_TARGETS:
            raise serializers.ValidationError(
                {"target_type": "Unsupported target type."}
            )
        bookmark, created = CommunityInteractionService.bookmark(
            user=request.user,
            target_type=target_type,
            target_id=target_id,
        )
        return Response(
            CommunityBookmarkResponseSerializer(bookmark).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, target_type: str, target_id: int):
        if target_type in CommunityTargetSelector.BOOKMARK_TARGETS:
            CommunityBookmark.objects.filter(
                user=request.user,
                **{f"{target_type}_id": target_id},
            ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
