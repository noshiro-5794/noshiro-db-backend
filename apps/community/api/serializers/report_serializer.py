from rest_framework import serializers

from apps.community.models import CommunityReport, ModerationAction
from apps.community.selectors.target_selector import CommunityTargetSelector


class CommunityReportCreateRequestSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(
        choices=sorted(CommunityTargetSelector.REPORT_TARGETS)
    )
    target_id = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(choices=CommunityReport.ReportReason.choices)
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )


class CommunityReportResolveRequestSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CommunityReport.ReportStatus.choices)
    action_type = serializers.ChoiceField(
        required=False,
        choices=ModerationAction.ActionType.choices,
    )
    moderation_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )


class CommunityReportListRequestSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        required=False,
        choices=CommunityReport.ReportStatus.choices,
    )


class CommunityReportUserResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nickname = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    def get_nickname(self, obj):
        profile = getattr(obj, "profile", None)
        if not profile:
            return ""
        return profile.nickname

    def get_avatar(self, obj):
        profile = getattr(obj, "profile", None)
        if not profile:
            return ""
        return profile.avatar


class CommunityReportResponseSerializer(serializers.ModelSerializer):
    reporter = serializers.SerializerMethodField()
    reported_user = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()
    resolved_by = serializers.SerializerMethodField()

    class Meta:
        model = CommunityReport
        fields = [
            "id",
            "reason",
            "description",
            "status",
            "reporter",
            "reported_user",
            "target",
            "resolved_by",
            "resolved_at",
            "created_at",
        ]

    def get_reporter(self, obj):
        return CommunityReportUserResponseSerializer(obj.reporter).data

    def get_reported_user(self, obj):
        if not obj.reported_user:
            return None
        return CommunityReportUserResponseSerializer(obj.reported_user).data

    def get_target(self, obj):
        for target_type in CommunityTargetSelector.REPORT_TARGETS:
            target_id = getattr(obj, f"{target_type}_id", None)
            if target_id:
                return {
                    "type": target_type,
                    "id": target_id,
                }
        return None

    def get_resolved_by(self, obj):
        if not obj.resolved_by:
            return None
        return CommunityReportUserResponseSerializer(obj.resolved_by).data
