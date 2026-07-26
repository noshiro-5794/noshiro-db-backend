from django.contrib.postgres.operations import RemoveIndexConcurrently
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("users", "0013_optimize_account_indexes"),
    ]

    operations = [
        RemoveIndexConcurrently(
            model_name="collection",
            name="idx_collection_user",
        ),
        RemoveIndexConcurrently(
            model_name="collectionitem",
            name="idx_ci_collection",
        ),
        RemoveIndexConcurrently(
            model_name="collectionitem",
            name="idx_ci_user_subject",
        ),
        RemoveIndexConcurrently(
            model_name="usersubject",
            name="idx_subject",
        ),
        RemoveIndexConcurrently(
            model_name="usertag",
            name="idx_user_tag_user",
        ),
        RemoveIndexConcurrently(
            model_name="userprofile",
            name="idx_user_nickname",
        ),
    ]
