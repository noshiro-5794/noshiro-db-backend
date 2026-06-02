from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.follow_serializer import (
    FollowerRelationResponseSerializer,
    FollowingRelationResponseSerializer,
)
from apps.community.selectors.follow_selector import UserFollowSelector
from apps.community.services.follow_service import UserFollowService
from apps.core.pagination import DefaultPageNumberPagination
from apps.core.response import success_response


class MyFollowToggleView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, target_user_id: int):
        relation, created = UserFollowService.follow_user(
            follower=request.user,
            target_user_id=target_user_id,
        )
        serializer = FollowingRelationResponseSerializer(relation)

        return success_response(
            data=serializer.data,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, target_user_id: int):
        UserFollowService.unfollow_user(
            follower=request.user,
            target_user_id=target_user_id,
        )

        return success_response(data=None, status_code=status.HTTP_204_NO_CONTENT)


class MyFollowingListView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserFollowSelector.list_following_relations(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = FollowingRelationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class MyFollowerListView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserFollowSelector.list_follower_relations(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = FollowerRelationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class UserFollowingListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = UserFollowSelector.get_user_by_id_or_raise(user_id=user_id)
        qs = UserFollowSelector.list_following_relations(user=user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = FollowingRelationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class UserFollowerListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = UserFollowSelector.get_user_by_id_or_raise(user_id=user_id)
        qs = UserFollowSelector.list_follower_relations(user=user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = FollowerRelationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)
