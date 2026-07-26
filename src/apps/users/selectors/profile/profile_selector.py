from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Count
from django.db.models.functions import TruncDate

from apps.users.models import Collection, User, UserSubject


class ProfileSelector:
    @staticmethod
    def get_stats(
        *,
        user: User,
        year: int,
        start_datetime: datetime,
        end_datetime: datetime,
        user_timezone: ZoneInfo,
    ) -> dict[str, Any]:
        mark_calendar = list(
            UserSubject.objects.filter(
                user=user,
                created_at__gte=start_datetime,
                created_at__lt=end_datetime,
            )
            .annotate(day=TruncDate("created_at", tzinfo=user_timezone))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        available_years = [
            value.year
            for value in UserSubject.objects.filter(user=user).datetimes(
                "created_at",
                "year",
                order="DESC",
                tzinfo=user_timezone,
            )
        ]
        library_totals = UserSubject.objects.filter(user=user).aggregate(
            subjects=Count("id", distinct=True),
            reviews=Count("reviews", distinct=True),
        )

        return {
            "year": year,
            "available_years": available_years,
            "totals": {
                **library_totals,
                "collections": Collection.objects.filter(user=user).count(),
                "marks_in_year": sum(item["count"] for item in mark_calendar),
            },
            "mark_calendar": [
                {
                    "date": item["day"].isoformat(),
                    "count": item["count"],
                }
                for item in mark_calendar
            ],
        }
