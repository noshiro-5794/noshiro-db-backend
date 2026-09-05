"""Generate idempotent title-similarity match candidates (AniList -> Bangumi)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ai.tasks import evaluate_match_candidate_task
from apps.index.services import provider_candidate_service


class Command(BaseCommand):
    help = (
        "Create title-similarity match candidates between AniList anime and "
        "Bangumi subject works. No entity is merged; AI evaluation is optional."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-similarity",
            type=float,
            default=0.6,
            help="pg_trgm similarity threshold for candidate titles.",
        )
        parser.add_argument("--top-k", type=int, default=5)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print candidate pairs without writing rows.",
        )
        parser.add_argument(
            "--evaluate",
            action="store_true",
            help="Dispatch AI evaluation for each newly created candidate.",
        )

    def handle(self, *args, **options):
        summary = provider_candidate_service.generate_candidates(
            min_similarity=options["min_similarity"],
            top_k=options["top_k"],
            create=not options["dry_run"],
        )
        if options["evaluate"] and not options["dry_run"]:
            for candidate_id in summary["created_ids"]:
                evaluate_match_candidate_task.delay(str(candidate_id))

        mode = "dry-run" if options["dry_run"] else "created"
        self.stdout.write(
            f"[{mode}] anilist_entities={summary['anilist_entities']} "
            f"candidates_created={summary['candidates_created']} "
            f"pairs_reported={len(summary['pairs'])}"
        )
        for pair in summary["pairs"][:50]:
            self.stdout.write(
                f"  {pair['similarity']:.2f} {pair['source_text'][:40]!r} "
                f"-> {pair['target_text'][:50]!r}"
            )
        if options["evaluate"] and not options["dry_run"]:
            self.stdout.write(
                f"AI evaluation dispatched for {len(summary['created_ids'])} candidates"
            )
