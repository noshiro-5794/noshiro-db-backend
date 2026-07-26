from django.conf import settings
from django.contrib.postgres.operations import RemoveIndexConcurrently
from django.db import migrations, models
from django.db.models import Q


def ensure_content_invariants(apps, schema_editor) -> None:
    post_model = apps.get_model("community", "CommunityPost")
    invalid_post_ids = list(
        post_model.objects.exclude(
            Q(post_type="subject", subject__isnull=False)
            | Q(post_type="status", subject__isnull=True)
        ).values_list("pk", flat=True)[:10]
    )

    report_model = apps.get_model("community", "CommunityReport")
    valid_report_target = (
        Q(
            post__isnull=False,
            comment__isnull=True,
            review__isnull=True,
            collection__isnull=True,
            activity__isnull=True,
        )
        | Q(
            post__isnull=True,
            comment__isnull=False,
            review__isnull=True,
            collection__isnull=True,
            activity__isnull=True,
        )
        | Q(
            post__isnull=True,
            comment__isnull=True,
            review__isnull=False,
            collection__isnull=True,
            activity__isnull=True,
        )
        | Q(
            post__isnull=True,
            comment__isnull=True,
            review__isnull=True,
            collection__isnull=False,
            activity__isnull=True,
        )
        | Q(
            post__isnull=True,
            comment__isnull=True,
            review__isnull=True,
            collection__isnull=True,
            activity__isnull=False,
        )
    )
    invalid_report_ids = list(
        report_model.objects.exclude(valid_report_target).values_list(
            "pk", flat=True
        )[:10]
    )

    if invalid_post_ids or invalid_report_ids:
        raise RuntimeError(
            "Community data violates the new content invariants. "
            f"Invalid post IDs: {invalid_post_ids}; "
            f"invalid report IDs: {invalid_report_ids}."
        )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("community", "0004_communitycomment_is_hidden_and_more"),
        ("index", "0007_enforce_source_identity"),
        ("users", "0014_remove_redundant_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            ensure_content_invariants,
            reverse_code=migrations.RunPython.noop,
        ),
        RemoveIndexConcurrently(
            model_name="userblock",
            name="idx_cub_blocked_user",
        ),
        RemoveIndexConcurrently(
            model_name="usermute",
            name="idx_cum_muted_user",
        ),
        migrations.AddConstraint(
            model_name="communitypost",
            constraint=models.CheckConstraint(
                condition=(
                    Q(post_type="subject", subject__isnull=False)
                    | Q(post_type="status", subject__isnull=True)
                ),
                name="ck_c_post_type_subject",
            ),
        ),
        migrations.AddConstraint(
            model_name="communityreport",
            constraint=models.CheckConstraint(
                condition=(
                    Q(
                        post__isnull=False,
                        comment__isnull=True,
                        review__isnull=True,
                        collection__isnull=True,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        comment__isnull=False,
                        review__isnull=True,
                        collection__isnull=True,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        comment__isnull=True,
                        review__isnull=False,
                        collection__isnull=True,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        comment__isnull=True,
                        review__isnull=True,
                        collection__isnull=False,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        comment__isnull=True,
                        review__isnull=True,
                        collection__isnull=True,
                        activity__isnull=False,
                    )
                ),
                name="ck_c_report_single_target",
            ),
        ),
    ]
