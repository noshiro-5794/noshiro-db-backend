from django.db import IntegrityError, transaction

from apps.users.models import User, UserProfile
from apps.users.exceptions import AvatarUploadFailed
from apps.users.storage.minio_client import minio_client


class ProfileService:

    @classmethod
    def get_or_create_profile(cls, *, user: User) -> UserProfile:
        try:
            return user.profile
        except UserProfile.DoesNotExist:
            return cls._create_default_profile(user=user)

    @staticmethod
    def _create_default_profile(*, user: User) -> UserProfile:
        base_nickname = f"user_{user.id}"
        for index in range(20):
            nickname = base_nickname if index == 0 else f"{base_nickname}_{index}"
            try:
                with transaction.atomic():
                    return UserProfile.objects.create(user=user, nickname=nickname)
            except IntegrityError:
                try:
                    return user.profile
                except UserProfile.DoesNotExist:
                    continue
        raise IntegrityError("Could not create a unique default profile nickname.")

    @classmethod
    @transaction.atomic
    def upload_avatar(cls, *, user: User, file_obj) -> str:
        profile = cls.get_or_create_profile(user=user)
        try:
            url = minio_client.upload_file(
                file_obj,
                folder=f"avatars/{user.id}",
            )
        except Exception as e:
            raise AvatarUploadFailed() from e
        profile.avatar = url
        profile.save(update_fields=["avatar"])
        return url

    @classmethod
    @transaction.atomic
    def update_profile(
        cls,
        *,
        user: User,
        nickname: str = None,
        bio: str = None,
        theme_color: str = None,
        language: str = None,
        appearance: str = None,
    ) -> UserProfile:
        profile = cls.get_or_create_profile(user=user)
        changed_fields = []
        if nickname is not None:
            profile.nickname = nickname
            changed_fields.append("nickname")
        if bio is not None:
            profile.bio = bio
            changed_fields.append("bio")
        if theme_color is not None:
            profile.theme_color = theme_color or "#7F6FB0"
            changed_fields.append("theme_color")
        if language is not None:
            profile.language = language
            changed_fields.append("language")
        if appearance is not None:
            profile.appearance = appearance
            changed_fields.append("appearance")
        if changed_fields:
            profile.save(update_fields=changed_fields)
        return profile
