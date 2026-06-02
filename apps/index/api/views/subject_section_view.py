from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.pagination import DefaultPageNumberPagination
from apps.core.response import success_response
from apps.index.api.serializers.subject_section_serializer import (
    SubjectCharacterResponseSerializer,
    SubjectEpisodeQuerySerializer,
    SubjectEpisodeResponseSerializer,
    SubjectRelationListResponseSerializer,
    SubjectStaffQuerySerializer,
    SubjectStaffRoleListResponseSerializer,
    SubjectStaffResponseSerializer,
)
from apps.index.selectors.subject_section_selector import SubjectSectionSelector


class SubjectEpisodePagination(DefaultPageNumberPagination):

    page_size = 96
    max_page_size = 96


class SubjectEpisodeListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, subject_id):
        query_serializer = SubjectEpisodeQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = SubjectSectionSelector.list_subject_episodes(
            subject_id=subject_id,
            **query_serializer.validated_data,
        )

        paginator = SubjectEpisodePagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = SubjectEpisodeResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


class SubjectEpisodeDetailView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, subject_id, episode_id):
        episode = SubjectSectionSelector.get_subject_episode_or_raise(
            subject_id=subject_id,
            episode_id=episode_id,
        )

        serializer = SubjectEpisodeResponseSerializer(episode)

        return success_response(data=serializer.data)


class SubjectStaffListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, subject_id):
        query_serializer = SubjectStaffQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = SubjectSectionSelector.list_subject_staff(
            subject_id=subject_id,
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = SubjectStaffResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


class SubjectStaffRoleListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, subject_id):
        roles = SubjectSectionSelector.list_subject_staff_roles(subject_id=subject_id)

        serializer = SubjectStaffRoleListResponseSerializer({"roles": list(roles)})

        return success_response(data=serializer.data)


class SubjectCharacterListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, subject_id):
        qs = SubjectSectionSelector.list_subject_characters(subject_id=subject_id)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = SubjectCharacterResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


class SubjectRelationListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, subject_id):
        relations, direction = SubjectSectionSelector.list_subject_relations(
            subject_id=subject_id,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(relations, request, view=self)

        relation_serializer = SubjectRelationListResponseSerializer()
        data = [
            relation_serializer.serialize_relation(relation, direction)
            for relation in page
        ]

        return paginator.get_paginated_response(data)
