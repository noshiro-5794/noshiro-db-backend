from django.db import models


class UserProfile(models.Model):
    class Language(models.TextChoices):
        AUTO = "auto", "Auto"
        EN_US = "en-US", "English"
        ZH_CN = "zh-CN", "Chinese"
        JA_JP = "ja-JP", "Japanese"

    class Appearance(models.TextChoices):
        AUTO = "auto", "Auto"
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="profile"
    )
    nickname = models.CharField(max_length=256, unique=True)
    avatar = models.URLField(max_length=1024, blank=True)
    bio = models.TextField(blank=True)
    language = models.CharField(
        max_length=16,
        choices=Language.choices,
        default=Language.AUTO,
    )
    appearance = models.CharField(
        max_length=16,
        choices=Appearance.choices,
        default=Appearance.AUTO,
    )
    theme_color = models.CharField(max_length=16, default="#7F6FB0")
    show_adult_content = models.BooleanField(default=False)
    adult_content_confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_profile"

    def __str__(self) -> str:
        return self.nickname
