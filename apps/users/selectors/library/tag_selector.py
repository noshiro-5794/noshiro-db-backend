from apps.users.models import UserTag, UserSubject, UserSubjectTag
from apps.users.exceptions import UserSubjectNotFound


class UserTagSelector:

    @staticmethod
    def list_my_tags(*, user):
        return UserTag.objects.filter(user=user).order_by("name", "id")

    @staticmethod
    def get_my_tag(*, user, tag_id: int):
        return UserTag.objects.filter(
            user=user,
            id=tag_id,
        ).first()

    @staticmethod
    def get_my_subject(*, user, user_subject_id: int):
        return (
            UserSubject.objects.select_related("user", "subject")
            .filter(
                user=user,
                id=user_subject_id,
            )
            .first()
        )

    @staticmethod
    def get_my_subject_by_subject_id(*, user, subject_id):
        return (
            UserSubject.objects.select_related("user", "subject")
            .filter(
                user=user,
                subject_id=subject_id,
            )
            .first()
        )

    @classmethod
    def get_my_subject_or_raise(cls, *, user, user_subject_id: int):
        user_subject = cls.get_my_subject(
            user=user,
            user_subject_id=user_subject_id,
        )

        if not user_subject:
            raise UserSubjectNotFound()

        return user_subject

    @classmethod
    def get_my_subject_by_subject_id_or_raise(cls, *, user, subject_id):
        user_subject = cls.get_my_subject_by_subject_id(
            user=user,
            subject_id=subject_id,
        )

        if not user_subject:
            raise UserSubjectNotFound()

        return user_subject

    @classmethod
    def list_subject_tags(cls, *, user, user_subject_id: int):
        user_subject = cls.get_my_subject_or_raise(
            user=user,
            user_subject_id=user_subject_id,
        )

        return UserTag.objects.filter(
            subject_relations__user_subject=user_subject
        ).order_by("name", "id")

    @classmethod
    def list_subject_tags_by_subject_id(cls, *, user, subject_id):
        user_subject = cls.get_my_subject_by_subject_id_or_raise(
            user=user,
            subject_id=subject_id,
        )

        return UserTag.objects.filter(
            subject_relations__user_subject=user_subject
        ).order_by("name", "id")

    @staticmethod
    def list_user_subject_tag_relations(*, user_subject):
        return (
            UserSubjectTag.objects.select_related("tag", "user_subject")
            .filter(user_subject=user_subject)
            .order_by("tag__name", "tag_id")
        )
