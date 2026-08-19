from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from .base import LegacySourceModel


class Anime(LegacySourceModel):
    subject = models.OneToOneField(
        "Subject", on_delete=models.CASCADE, primary_key=True, related_name="anime"
    )

    aliases = ArrayField(models.CharField(max_length=256), default=list, blank=True)
    titles = models.JSONField(default=dict, blank=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    anime_type = models.CharField(max_length=64, blank=True)
    anime_source = models.CharField(max_length=64, blank=True)
    official_websites = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    image_original = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    image_extra = models.JSONField(default=list, blank=True)
    anime_status = models.CharField(max_length=256, blank=True)
    ep_total = models.IntegerField(blank=True, null=True)
    broadcast = models.JSONField(default=dict, blank=True)
    broadcast_season = models.JSONField(default=dict, blank=True)
    external_links = models.JSONField(default=dict, blank=True)
    genres = models.ManyToManyField(
        "Genre", through="AnimeGenreRelation", related_name="animes", blank=True
    )

    class Meta:
        db_table = "anime"
        constraints = [
            models.UniqueConstraint(
                fields=["info_source", "id_source"],
                name="uq_anime_info_id_source",
            )
        ]
        indexes = [GinIndex(fields=["aliases"], name="idx_anime_aliases")]

    def __str__(self) -> str:
        return self.subject.title


class AnimeGenreRelation(models.Model):
    anime = models.ForeignKey(
        "Anime", on_delete=models.CASCADE, related_name="genre_relations"
    )
    genre = models.ForeignKey(
        "Genre", on_delete=models.CASCADE, related_name="anime_relations"
    )

    class Meta:
        db_table = "anime_genre_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["anime", "genre"],
                name="uq_anime_genre",
            )
        ]
