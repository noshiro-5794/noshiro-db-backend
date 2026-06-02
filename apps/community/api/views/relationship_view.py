from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.relationship_serializer import (
    RelationshipReasonRequestSerializer,
    UserBlockResponseSerializer,
    UserMuteResponseSerializer,
)
from apps.community.selectors.relationship_selector import UserRelationshipSelector
from apps.community.services.relationship_service import UserRelationshipService
from apps.core.pagination import DefaultPageNumberPagination
from apps.core.response import success_response


class MyBlockListView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserRelationshipSelector.list_block_relations(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = UserBlockResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class MyBlockToggleView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, target_user_id: int):
        serializer = RelationshipReasonRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        relation, created = UserRelationshipService.block_user(
            user=request.user,
            target_user_id=target_user_id,
            reason=serializer.validated_data.get("reason", ""),
        )
        output_serializer = UserBlockResponseSerializer(relation)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, target_user_id: int):
        UserRelationshipService.unblock_user(
            user=request.user,
            target_user_id=target_user_id,
        )

        return success_response(data=None, status_code=status.HTTP_204_NO_CONTENT)


class MyMuteListView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserRelationshipSelector.list_mute_relations(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = UserMuteResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class MyMuteToggleView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, target_user_id: int):
        serializer = RelationshipReasonRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        relation, created = UserRelationshipService.mute_user(
            user=request.user,
            target_user_id=target_user_id,
            reason=serializer.validated_data.get("reason", ""),
        )
        output_serializer = UserMuteResponseSerializer(relation)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, target_user_id: int):
        UserRelationshipService.unmute_user(
            user=request.user,
            target_user_id=target_user_id,
        )

        return success_response(data=None, status_code=status.HTTP_204_NO_CONTENT)
