from collections.abc import Iterable, Mapping
from functools import cache

from drf_spectacular.utils import inline_serializer
from rest_framework import serializers


class ProblemDetailsSerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    status = serializers.IntegerField(min_value=400, max_value=599)
    detail = serializers.CharField()
    instance = serializers.CharField(required=False)
    trace_id = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    errors = serializers.JSONField(required=False)


class PaginationQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=64)


class CursorPaginationQuerySerializer(serializers.Serializer):
    cursor = serializers.CharField(required=False)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=64)


@cache
def paginated_response(name: str, item_serializer):
    return inline_serializer(
        name=name,
        fields={
            "count": serializers.IntegerField(min_value=0),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": item_serializer(many=True),
        },
    )


@cache
def cursor_paginated_response(name: str, item_serializer):
    return inline_serializer(
        name=name,
        fields={
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": item_serializer(many=True),
        },
    )


def api_responses(
    success: Mapping[int, object],
    *,
    errors: Iterable[int] = (400, 401, 403, 404),
) -> dict[int | tuple[int, str], object]:
    responses = dict(success)
    responses.update(
        {
            (status_code, "application/problem+json"): ProblemDetailsSerializer
            for status_code in errors
            if status_code not in responses
        }
    )
    return responses
