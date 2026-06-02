from django.db import transaction, IntegrityError

from apps.users.models import UserTag, UserSubjectTag
from apps.users.exceptions import TagNotFound, TagAlreadyExists, InvalidTagIds
from apps.users.selectors.library.tag_selector import UserTagSelector


class UserTagService:

    @staticmethod
    @transaction.atomic
    def create_tag(*, user, name: str):
        name = name.strip()

        try:
            tag, created = UserTag.objects.get_or_create(
                user=user,
                name=name,
            )
        except IntegrityError:
            tag = UserTag.objects.get(
                user=user,
                name=name,
            )
            created = False

        return tag, created

    @staticmethod
    @transaction.atomic
    def update_tag(*, user, tag_id: int, name: str):
        tag = UserTagSelector.get_my_tag(
            user=user,
            tag_id=tag_id,
        )

        if not tag:
            raise TagNotFound()

        name = name.strip()

        exists = (
            UserTag.objects.filter(
                user=user,
                name=name,
            )
            .exclude(id=tag.id)
            .exists()
        )

        if exists:
            raise TagAlreadyExists()

        tag.name = name
        tag.save(update_fields=["name"])

        return tag

    @staticmethod
    @transaction.atomic
    def delete_tag(*, user, tag_id: int):
        tag = UserTagSelector.get_my_tag(
            user=user,
            tag_id=tag_id,
        )

        if not tag:
            raise TagNotFound()

        tag.delete()

    @staticmethod
    @transaction.atomic
    def replace_subject_tags(
        *,
        user,
        user_subject_id: int,
        tag_ids=None,
        tag_names=None,
    ):
        user_subject = UserTagSelector.get_my_subject_or_raise(
            user=user,
            user_subject_id=user_subject_id,
        )

        return UserTagService.replace_user_subject_tags(
            user=user,
            user_subject=user_subject,
            tag_ids=tag_ids,
            tag_names=tag_names,
        )

    @staticmethod
    @transaction.atomic
    def replace_subject_tags_by_subject_id(
        *,
        user,
        subject_id,
        tag_ids=None,
        tag_names=None,
    ):
        user_subject = UserTagSelector.get_my_subject_by_subject_id_or_raise(
            user=user,
            subject_id=subject_id,
        )

        return UserTagService.replace_user_subject_tags(
            user=user,
            user_subject=user_subject,
            tag_ids=tag_ids,
            tag_names=tag_names,
        )

    @staticmethod
    def replace_user_subject_tags(*, user, user_subject, tag_ids=None, tag_names=None):

        tag_ids = list(dict.fromkeys(tag_ids or []))
        tag_names = list(dict.fromkeys(tag_names or []))

        tags_by_id = list(
            UserTag.objects.filter(
                user=user,
                id__in=tag_ids,
            ).order_by("id")
        )

        found_tag_ids = {tag.id for tag in tags_by_id}
        invalid_tag_ids = [tag_id for tag_id in tag_ids if tag_id not in found_tag_ids]

        if invalid_tag_ids:
            raise InvalidTagIds()

        tags_by_name = []
        for tag_name in tag_names:
            try:
                tag, _ = UserTag.objects.get_or_create(
                    user=user,
                    name=tag_name.strip(),
                )
            except IntegrityError:
                tag = UserTag.objects.get(
                    user=user,
                    name=tag_name.strip(),
                )
            tags_by_name.append(tag)

        tags = []
        seen_tag_ids = set()
        for tag in [*tags_by_id, *tags_by_name]:
            if tag.id in seen_tag_ids:
                continue
            seen_tag_ids.add(tag.id)
            tags.append(tag)

        UserSubjectTag.objects.filter(
            user_subject=user_subject,
        ).delete()

        UserSubjectTag.objects.bulk_create(
            [
                UserSubjectTag(
                    user_subject=user_subject,
                    tag=tag,
                )
                for tag in tags
            ],
            ignore_conflicts=True,
        )

        return UserTagSelector.list_subject_tags(
            user=user,
            user_subject_id=user_subject.id,
        )
