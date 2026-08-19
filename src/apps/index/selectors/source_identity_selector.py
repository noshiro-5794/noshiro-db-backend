from django.db.models import Prefetch

from apps.index.models import SourceRecord, SubjectExternalIdentity


class SourceIdentitySelector:
    @staticmethod
    def active_subject_identities():
        return SubjectExternalIdentity.objects.filter(
            source_record__status=SourceRecord.Status.ACTIVE,
        ).select_related("source_record__namespace__provider")

    @classmethod
    def subject_prefetch(cls, *, lookup: str = "external_identities") -> Prefetch:
        return Prefetch(
            lookup,
            queryset=cls.active_subject_identities().order_by(
                "-is_primary",
                "source_record__namespace__provider__slug",
                "source_record__namespace__slug",
                "source_record__external_id",
            ),
            to_attr="catalog_identities",
        )
