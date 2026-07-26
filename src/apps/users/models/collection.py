from django.db import models
from django.db.models import Q


class Collection(models.Model):
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="collections"
    )
    name = models.CharField(max_length=256)
    simple_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)

    class Meta:
        db_table = "collection"
        constraints = [
            models.CheckConstraint(
                condition=Q(simple_rating__isnull=True)
                | (Q(simple_rating__gte=1) & Q(simple_rating__lte=5)),
                name="ck_collection_simple_rating",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_public"], name="idx_collection_public"),
        ]

    def __str__(self) -> str:
        return f"user={self.user_id} collection={self.name}"


class CollectionItem(models.Model):
    collection = models.ForeignKey(
        "Collection", on_delete=models.CASCADE, related_name="items"
    )
    user_subject = models.ForeignKey(
        "UserSubject", on_delete=models.CASCADE, related_name="collection_items"
    )
    order = models.IntegerField(default=0)
    relation = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "collection_item"
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "user_subject"], name="uq_collection_user_subject"
            )
        ]

    def __str__(self) -> str:
        return f"collection={self.collection_id} user_subject={self.user_subject_id}"
