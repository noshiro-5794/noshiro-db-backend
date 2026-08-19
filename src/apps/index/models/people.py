from django.db import models

from .base import LegacySourceModel


class Staff(LegacySourceModel):
    contributor = models.OneToOneField(
        "Contributor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_projection",
    )
    name = models.CharField(max_length=256, blank=True)
    description = models.TextField(blank=True)
    gender = models.CharField(max_length=64, blank=True)
    birth = models.JSONField(default=dict, blank=True)
    type = models.CharField(max_length=64, blank=True)
    career = models.JSONField(default=list, blank=True)
    image_original = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    infobox = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "staff"
        constraints = [
            models.UniqueConstraint(
                fields=["info_source", "id_source"],
                name="uq_staff_info_id_source",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Character(LegacySourceModel):
    entity = models.OneToOneField(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="character_projection",
    )
    name = models.CharField(max_length=256, blank=True)
    description = models.TextField(blank=True)
    gender = models.CharField(max_length=64, blank=True)
    birth = models.JSONField(default=dict, blank=True)
    type = models.CharField(max_length=64, blank=True)
    blood_type = models.CharField(max_length=64, blank=True)
    image_original = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    infobox = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "character"
        constraints = [
            models.UniqueConstraint(
                fields=["info_source", "id_source"],
                name="uq_character_info_id_source",
            )
        ]

    def __str__(self) -> str:
        return self.name
