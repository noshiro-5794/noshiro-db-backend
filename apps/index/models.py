import uuid

from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex


class Source(models.Model):

    info_source = models.CharField(max_length=64)
    id_source   = models.CharField(max_length=64)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=['info_source', 'id_source'],
                name='uq_%(class)s_info_id_source'
            )
        ]
        indexes = [
            models.Index(
                fields=['info_source', 'id_source'],
                name='idx_%(class)s_info_id_source'
            ),
        ]


class Staff(Source):

    name            = models.CharField(max_length=256, blank=True)
    description     = models.TextField(blank=True)
    gender          = models.CharField(max_length=64, blank=True)
    birth           = models.JSONField(default=dict, blank=True)
    type            = models.CharField(max_length=64, blank=True)
    career          = models.JSONField(default=list, blank=True)
    image_original  = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    infobox         = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'staff'

    def __str__(self):
        return self.name


class Character(Source):

    name            = models.CharField(max_length=256, blank=True)
    description     = models.TextField(blank=True)
    gender          = models.CharField(max_length=64, blank=True)
    birth           = models.JSONField(default=dict, blank=True)
    type            = models.CharField(max_length=64, blank=True)
    blood_type      = models.CharField(max_length=64, blank=True)
    image_original  = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    infobox         = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'character'

    def __str__(self):
        return self.name


class Episode(Source):

    title       = models.CharField(max_length=256, blank=True)
    type        = models.CharField(max_length=64, blank=True)
    ep_num      = models.IntegerField(blank=True, null=True)
    sort        = models.IntegerField(blank=True, null=True)
    duration    = models.DurationField(blank=True, null=True)
    date        = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True)
    subject     = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='episodes')

    class Meta:
        db_table = 'episode'

    def __str__(self):
        return self.title


class Subject(Source):

    class SubjectType(models.TextChoices):
        ANIME   = "anime", "Anime"
        GALGAME = "galgame", "Galgame"
        GAME    = "game", "Game"
        MANGA   = "manga", "Manga"
        NOVEL   = "novel", "Novel"
        BOOK    = "book", "Book"
        MUSIC   = "music", "Music"
        OTHER   = "other", "Other"

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject_type    = models.CharField(max_length=64, choices=SubjectType.choices, blank=True)
    title           = models.CharField(max_length=256, blank=True)
    title_cn        = models.CharField(max_length=256, blank=True)
    date            = models.DateField(blank=True, null=True)
    image_original  = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    platform        = models.CharField(max_length=256, blank=True)
    description     = models.TextField(blank=True)
    nsfw            = models.BooleanField(default=False)
    series          = models.BooleanField(default=False)
    volumes         = models.IntegerField(blank=True, null=True)
    eps             = models.IntegerField(blank=True, null=True)
    total_episodes  = models.IntegerField(blank=True, null=True)
    infobox         = models.JSONField(default=list, blank=True)
    tags            = models.JSONField(default=list, blank=True)
    staff           = models.ManyToManyField('Staff', through='SubjectStaffRelation', related_name='subjects', blank=True)
    characters      = models.ManyToManyField('Character', through='SubjectCharacterRelation', related_name='subjects', blank=True)

    class Meta:
        db_table = 'subject'
        indexes = [
            GinIndex(
                name="idx_subject_title",
                fields=["title"],
                opclasses=["gin_trgm_ops"]
            ),
            GinIndex(
                name="idx_subject_title_cn",
                fields=["title_cn"],
                opclasses=["gin_trgm_ops"]
            )
        ]

    def __str__(self):
        return f'[{self.subject_type}] {self.title or "Untitled"} ({self.date or "Unknown"})'


class CalendarSubject(models.Model):

    subject = models.OneToOneField(
        "Subject", on_delete=models.CASCADE, related_name="calendar_entry"
    )
    weekday_en = models.CharField(max_length=16, blank=True)
    collection_doing = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "calendar_subject"
        indexes = [
            models.Index(fields=["weekday_en"], name="idx_cal_weekday_en"),
            models.Index(
                fields=["weekday_en", "-collection_doing"],
                name="idx_cal_weekday_doing",
            ),
        ]

    def __str__(self):
        return f"{self.weekday_en}: {self.subject}"


class SubjectStaffRelation(models.Model):

    subject = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="staff_relations"
    )
    staff = models.ForeignKey(
        "Staff", on_delete=models.CASCADE, related_name="subject_relations"
    )
    role = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'subject_staff_relation'
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "staff", "role"],
                name="uq_subject_staff_role"
            )
        ]
        indexes = [
            models.Index(fields=["subject", "role"], name="idx_subj_stf_sr"),
        ]

    def __str__(self):
        return f'{self.subject} - {self.staff} ({self.role})'


class SubjectCharacterRelation(models.Model):

    subject = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="character_relations"
    )
    character = models.ForeignKey(
        "Character", on_delete=models.CASCADE, related_name="subject_relations"
    )
    role = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'subject_character_relation'
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "character", "role"],
                name="uq_subject_character_role"
            )
        ]
        indexes = [
            models.Index(fields=["subject", "role"], name="idx_subj_char_sr"),
        ]

    def __str__(self):
        return f'{self.subject} - {self.character} ({self.role})'


class SubjectCharacterActorRelation(models.Model):

    subject = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="character_actor_relations"
    )
    character = models.ForeignKey(
        "Character", on_delete=models.CASCADE, related_name="actor_relations"
    )
    actor = models.ForeignKey(
        "Staff", on_delete=models.CASCADE, related_name="voice_roles"
    )

    class Meta:
        db_table = "subject_character_actor_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "character", "actor"],
                name="uq_subject_character_actor"
            )
        ]
        indexes = [
            models.Index(fields=["subject", "character"], name="idx_subj_char_act_sc"),
            models.Index(fields=["character", "actor"], name="idx_subj_char_act_ca"),
        ]

    def __str__(self):
        return f'{self.subject} - {self.character} ({self.actor})'


class SubjectSubjectRelation(models.Model):

    source = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="outgoing_relations"
    )
    target = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="incoming_relations"
    )
    relation = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'subject_subject_relation'
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'target', 'relation'],
                name='uq_subject_subject_relation'
            )
        ]
        indexes = [
            models.Index(fields=["source", "relation"], name="idx_subj_subj_sr"),
            models.Index(fields=["target"], name="idx_subj_subj_t"),
        ]

    def __str__(self):
        return f'{self.source} -> {self.target} ({self.relation})'


class Genre(models.Model):

    name = models.CharField(max_length=256, unique=True)

    class Meta:
        db_table = 'genre'

    def __str__(self):
        return self.name


class Anime(Source):

    subject = models.OneToOneField(
        "Subject", on_delete=models.CASCADE, primary_key=True, related_name="anime"
    )

    aliases             = ArrayField(models.CharField(max_length=256), default=list, blank=True)
    titles              = models.JSONField(default=dict, blank=True)
    start_date          = models.DateField(blank=True, null=True)
    end_date            = models.DateField(blank=True, null=True)
    anime_type          = models.CharField(max_length=64, blank=True)
    anime_source        = models.CharField(max_length=64, blank=True)
    official_websites   = models.JSONField(default=list, blank=True)
    description         = models.TextField(blank=True)
    image_original      = models.URLField(max_length=1024, blank=True)
    image_thumbnail     = models.URLField(max_length=1024, blank=True)
    image_extra         = models.JSONField(default=list, blank=True)
    anime_status        = models.CharField(max_length=256, blank=True)
    ep_total            = models.IntegerField(blank=True, null=True)
    broadcast           = models.JSONField(default=dict, blank=True)
    broadcast_season    = models.JSONField(default=dict, blank=True)
    external_links      = models.JSONField(default=dict, blank=True)
    genres              = models.ManyToManyField('Genre', through='AnimeGenreRelation', related_name='animes', blank=True)

    class Meta:
        db_table = 'anime'
        indexes = [
            GinIndex(fields=['aliases'], name='idx_anime_aliases')
        ]

    def __str__(self):
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
        unique_together = ("anime", "genre")


class Galgame(Source):

    subject = models.OneToOneField(
        "Subject", on_delete=models.CASCADE, primary_key=True, related_name="galgame"
    )

    aliases         = ArrayField(models.CharField(max_length=256), default=list, blank=True)
    titles          = models.JSONField(default=dict, blank=True)
    released_date   = models.DateField(blank=True, null=True)
    description     = models.TextField(blank=True)
    image_original  = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    screenshots     = models.JSONField(default=list, blank=True)
    platforms       = models.JSONField(default=list, blank=True)
    galgame_status  = models.CharField(max_length=64, blank=True)
    external_links  = models.JSONField(default=dict, blank=True)
    genres          = models.ManyToManyField('Genre', through='GalgameGenreRelation', related_name='galgames', blank=True)

    class Meta:
        db_table = 'galgame'
        indexes = [
            GinIndex(fields=['aliases'], name='idx_galgame_aliases')
        ]

    def __str__(self):
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
        unique_together = ("galgame", "genre")

    def __str__(self):
        return self.genre
