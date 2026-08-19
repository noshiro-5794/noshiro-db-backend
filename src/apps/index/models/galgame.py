from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from .base import LegacySourceModel


class Galgame(LegacySourceModel):
    subject = models.OneToOneField(
        "Subject", on_delete=models.CASCADE, primary_key=True, related_name="galgame"
    )

    aliases = ArrayField(models.CharField(max_length=256), default=list, blank=True)
    titles = models.JSONField(default=dict, blank=True)
    released_date = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True)
    image_original = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    screenshots = models.JSONField(default=list, blank=True)
    platforms = models.JSONField(default=list, blank=True)
    galgame_status = models.CharField(max_length=64, blank=True)
    external_links = models.JSONField(default=dict, blank=True)
    genres = models.ManyToManyField(
        "Genre", through="GalgameGenreRelation", related_name="galgames", blank=True
    )

    class Meta:
        db_table = "galgame"
        constraints = [
            models.UniqueConstraint(
                fields=["info_source", "id_source"],
                name="uq_galgame_info_id_source",
            )
        ]
        indexes = [GinIndex(fields=["aliases"], name="idx_galgame_aliases")]

    def __str__(self) -> str:
        return self.subject.title


class GalgameGenreRelation(models.Model):
    galgame = models.ForeignKey(
        "Galgame", on_delete=models.CASCADE, related_name="genre_relations"
    )
    genre = models.ForeignKey(
        "Genre", on_delete=models.CASCADE, related_name="galgame_relations"
    )

    class Meta:
        db_table = "galgame_genre_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["galgame", "genre"],
                name="uq_galgame_genre",
            )
        ]

    def __str__(self) -> str:
        return str(self.genre)
