from apps.index.models import CalendarSubject


class CalendarSelector:
    @staticmethod
    def list_calendar(*, weekday_en=None):
        qs = CalendarSubject.objects.select_related("subject")
        if weekday_en:
            qs = qs.filter(weekday_en=weekday_en)
        return qs.order_by(
            "weekday_en", "-collection_doing", "subject__title", "subject_id"
        )
