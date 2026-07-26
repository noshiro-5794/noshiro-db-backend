from types import SimpleNamespace

from apps.community.api.serializers.activity_serializer import (
    ActivityListRequestSerializer,
    FeedListRequestSerializer,
)
from apps.community.api.serializers.common_serializer import (
    CommunityUserResponseSerializer,
)
from apps.community.api.serializers.post_serializer import (
    CommunityPostCreateRequestSerializer,
    CommunityPostListRequestSerializer,
)
from apps.community.api.serializers.report_serializer import (
    CommunityReportResolveRequestSerializer,
)
from apps.community.models import CommunityPost, CommunityReport


def test_user_summary_does_not_fall_back_to_email() -> None:
    user = SimpleNamespace(id=1, email="private@example.com")

    assert CommunityUserResponseSerializer(user).data == {
        "id": 1,
        "nickname": "",
        "avatar": "",
    }


def test_community_query_serializers_reject_invalid_values() -> None:
    post_query = CommunityPostListRequestSerializer(data={"ordering": "author"})
    activity_query = ActivityListRequestSerializer(data={"activity_type": "unknown"})
    feed_query = FeedListRequestSerializer(data={"include_self": "sometimes"})

    assert not post_query.is_valid()
    assert not activity_query.is_valid()
    assert not feed_query.is_valid()


def test_post_content_has_an_api_size_limit() -> None:
    serializer = CommunityPostCreateRequestSerializer(
        data={"content": "x" * 10_001},
    )

    assert not serializer.is_valid()
    assert "content" in serializer.errors


def test_rejected_report_can_not_apply_moderation() -> None:
    serializer = CommunityReportResolveRequestSerializer(
        data={"status": "rejected", "action_type": "hide"},
    )

    assert not serializer.is_valid()
    assert "non_field_errors" in serializer.errors


def test_community_models_declare_content_invariants() -> None:
    post_constraints = {
        constraint.name for constraint in CommunityPost._meta.constraints
    }
    report_constraints = {
        constraint.name for constraint in CommunityReport._meta.constraints
    }

    assert "ck_c_post_type_subject" in post_constraints
    assert "ck_c_report_single_target" in report_constraints
