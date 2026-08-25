import uuid

from django.db import models
from django.utils import timezone


class SourceArtifact(models.Model):
    """Content-addressed evidence captured by a tool.

    Large content belongs in object storage. The database stores only a bounded
    excerpt, retrieval metadata, and the immutable content hash.
    """

    class Kind(models.TextChoices):
        WEB_PAGE = "web_page", "Web page"
        SEARCH_RESULT = "search_result", "Search result"
        INTERNAL_SNAPSHOT = "internal_snapshot", "Internal snapshot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tool_invocation = models.ForeignKey(
        "ToolInvocation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="artifacts",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    source_url = models.URLField(max_length=2048, blank=True)
    content_hash = models.CharField(max_length=64)
    mime_type = models.CharField(max_length=128, blank=True)
    byte_size = models.PositiveBigIntegerField(null=True, blank=True)
    excerpt = models.TextField(blank=True)
    object_key = models.CharField(max_length=1024, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    license_info = models.CharField(max_length=512, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "source_artifact"
        indexes = [
            models.Index(fields=["content_hash"], name="idx_source_artifact_hash"),
            models.Index(
                fields=["kind", "-fetched_at"], name="idx_src_artifact_kind_fetch"
            ),
        ]
