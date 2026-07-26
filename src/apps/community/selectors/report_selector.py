from apps.community.exceptions import CommunityReportNotFound
from apps.community.models import CommunityReport


class CommunityReportSelector:
    @staticmethod
    def base_queryset():
        return CommunityReport.objects.select_related(
            "reporter",
            "reporter__profile",
            "reported_user",
            "reported_user__profile",
            "resolved_by",
            "post",
            "comment",
            "review",
            "collection",
            "activity",
        )

    @classmethod
    def list_my_reports(cls, *, user):
        return cls.base_queryset().filter(reporter=user).order_by("-created_at", "-id")

    @classmethod
    def list_reports_for_staff(cls, *, status=None):
        qs = cls.base_queryset()

        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-created_at", "-id")

    @classmethod
    def get_report_for_staff_or_raise(cls, *, report_id: int):
        report = cls.base_queryset().filter(id=report_id).first()

        if not report:
            raise CommunityReportNotFound()

        return report
