from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.api.serializers.follows import (
    FollowingRelationResponseSerializer,
)
from apps.community.api.serializers.relationships import (
    RelationshipReasonRequestSerializer,
    UserBlockResponseSerializer,
    UserMuteResponseSerializer,
)
from apps.community.models import Activity, UserBlock, UserFollow, UserMute
from apps.community.selectors.follow_selector import UserFollowSelector
from apps.community.selectors.relationship_selector import UserRelationshipSelector
from apps.community.services.follow_service import UserFollowService
from apps.community.services.relationship_service import UserRelationshipService
from shared.api.contracts import api_responses


@extend_schema_view(
    put=extend_schema(
        request=None,
        responses=api_responses(
            {
                200: FollowingRelationResponseSerializer,
                201: FollowingRelationResponseSerializer,
            }
        ),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class FollowView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, target_user_id: int):
        relation, created = UserFollowService.follow_user(
            follower=request.user, target_user_id=target_user_id
        )
        return Response(
            FollowingRelationResponseSerializer(relation).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, target_user_id: int):
        target = UserFollowSelector.get_user_by_id_or_raise(user_id=target_user_id)
        UserFollow.objects.filter(follower=request.user, following=target).delete()
        Activity.objects.filter(
            activity_type=Activity.ActivityType.USER_FOLLOWED,
            user=request.user,
            target_user=target,
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    put=extend_schema(
        request=RelationshipReasonRequestSerializer,
        responses=api_responses(
            {200: UserBlockResponseSerializer, 201: UserBlockResponseSerializer}
        ),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class BlockView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, target_user_id: int):
        serializer = RelationshipReasonRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        relation, created = UserRelationshipService.block_user(
            user=request.user,
            target_user_id=target_user_id,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(
            UserBlockResponseSerializer(relation).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, target_user_id: int):
        target = UserRelationshipSelector.get_user_by_id_or_raise(
            user_id=target_user_id
        )
        UserBlock.objects.filter(user=request.user, blocked_user=target).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    put=extend_schema(
        request=RelationshipReasonRequestSerializer,
        responses=api_responses(
            {200: UserMuteResponseSerializer, 201: UserMuteResponseSerializer}
        ),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class MuteView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, target_user_id: int):
        serializer = RelationshipReasonRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        relation, created = UserRelationshipService.mute_user(
            user=request.user,
            target_user_id=target_user_id,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(
            UserMuteResponseSerializer(relation).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, target_user_id: int):
        target = UserRelationshipSelector.get_user_by_id_or_raise(
            user_id=target_user_id
        )
        UserMute.objects.filter(user=request.user, muted_user=target).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
