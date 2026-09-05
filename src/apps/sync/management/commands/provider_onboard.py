"""Idempotently register a catalog provider with explicit usage policies."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.index.models import Provider
from apps.sync.providers.anilist import ANILIST_SOURCE
from apps.sync.providers.bangumi import BANGUMI_SOURCE
from apps.sync.providers.contracts import CatalogSourceSpec
from apps.sync.providers.vndb import VNDB_SOURCE

PROVIDER_SPECS: dict[str, CatalogSourceSpec] = {
    spec.slug: spec for spec in (VNDB_SOURCE, BANGUMI_SOURCE, ANILIST_SOURCE)
}

POLICY_FIELDS = {
    "storage": "storage_policy",
    "redistribution": "redistribution_policy",
    "commercial_use": "commercial_use_policy",
    "ai_usage": "ai_usage_policy",
}


class Command(BaseCommand):
    help = (
        "Create or update a catalog provider row with explicit usage policies. "
        "Dry-runs by default; pass --apply to persist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "provider",
            choices=sorted(PROVIDER_SPECS),
            help="Provider slug to register.",
        )
        parser.add_argument(
            "--policy",
            action="append",
            default=[],
            metavar="storage=allowed",
            help=(
                "Usage policy assignment, repeatable: "
                "storage|redistribution|commercial_use|ai_usage="
                "unknown|allowed|restricted|forbidden"
            ),
        )
        parser.add_argument(
            "--enable", action="store_true", help="Enable the provider."
        )
        parser.add_argument(
            "--disable", action="store_true", help="Disable the provider."
        )
        parser.add_argument(
            "--terms-checked",
            action="store_true",
            help="Mark provider terms as reviewed today.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist changes (default is a read-only dry run).",
        )

    def handle(self, *args, **options):
        spec = PROVIDER_SPECS[options["provider"]]
        if options["enable"] and options["disable"]:
            raise CommandError("--enable and --disable are mutually exclusive.")
        policies = self._parse_policies(options["policy"])
        desired_enabled: bool | None = None
        if options["enable"]:
            desired_enabled = True
        elif options["disable"]:
            desired_enabled = False

        if options["apply"]:
            provider, created = Provider.objects.get_or_create(
                slug=spec.slug,
                defaults={
                    "name": spec.name,
                    "base_url": spec.base_url,
                    "terms_url": spec.terms_url,
                    "attribution_url": spec.attribution_url,
                    "license_name": spec.license_name,
                    "is_enabled": bool(desired_enabled),
                },
            )
            changes: dict[str, str] = {}
            if created:
                changes["name"] = spec.name
                changes["base_url"] = spec.base_url
                changes["terms_url"] = spec.terms_url
                changes["attribution_url"] = spec.attribution_url
                changes["license_name"] = spec.license_name
                changes["is_enabled"] = str(bool(desired_enabled)).lower()
            elif desired_enabled is not None and provider.is_enabled != desired_enabled:
                changes["is_enabled"] = (
                    f"{str(provider.is_enabled).lower()} -> "
                    f"{str(desired_enabled).lower()}"
                )
            for policy_name, field_name in POLICY_FIELDS.items():
                if policy_name in policies:
                    current = getattr(provider, field_name)
                    chosen = policies[policy_name]
                    if current != chosen:
                        changes[f"policy:{policy_name}"] = f"{current} -> {chosen}"
            if options["terms_checked"] and provider.terms_checked_at is None:
                changes["terms_checked_at"] = "now"
            if options["enable"]:
                provider.is_enabled = True
            if options["disable"]:
                provider.is_enabled = False
            if options["terms_checked"]:
                provider.terms_checked_at = timezone.now()
            for policy_name, field_name in POLICY_FIELDS.items():
                if policy_name in policies:
                    setattr(provider, field_name, policies[policy_name])
            provider.save()
            verb = "created" if created else "updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"Provider {spec.slug} {verb}: "
                    + (
                        ", ".join(f"{k}={v}" for k, v in changes.items())
                        or "no changes"
                    )
                )
            )
            return

        existing = Provider.objects.filter(slug=spec.slug).first()
        self.stdout.write(
            f"[dry-run] Provider {spec.slug} "
            + ("would be created" if existing is None else "exists")
        )
        if existing is not None:
            planned: dict[str, str] = {}
            if desired_enabled is not None and existing.is_enabled != desired_enabled:
                planned["is_enabled"] = (
                    f"{str(existing.is_enabled).lower()} -> "
                    f"{str(desired_enabled).lower()}"
                )
            for policy_name, field_name in POLICY_FIELDS.items():
                if policy_name in policies:
                    current = getattr(existing, field_name)
                    if current != policies[policy_name]:
                        planned[f"policy:{policy_name}"] = (
                            f"{current} -> {policies[policy_name]}"
                        )
            if options["terms_checked"] and existing.terms_checked_at is None:
                planned["terms_checked_at"] = "now"
            for key, value in planned.items():
                self.stdout.write(f"  {key}: {value}")
            if not planned:
                self.stdout.write("  no changes")
        self.stdout.write(
            self.style.WARNING(
                "Re-run with --apply to persist these changes; explicit policies "
                "are required for storage/redistribution/ai use before syncing."
            )
        )

    @staticmethod
    def _parse_policies(raw: list[str]) -> dict[str, str]:
        valid_values = {choice for choice, _ in Provider.UsagePolicy.choices}
        policies: dict[str, str] = {}
        for assignment in raw:
            if "=" not in assignment:
                raise CommandError(
                    f"Invalid --policy '{assignment}'; use policy=value."
                )
            key, value = assignment.split("=", 1)
            key = key.strip().lower()
            value = value.strip().lower()
            if key not in POLICY_FIELDS:
                raise CommandError(
                    f"Unknown policy '{key}'; expected one of "
                    + ", ".join(POLICY_FIELDS)
                )
            if value not in valid_values:
                raise CommandError(
                    f"Invalid value '{value}' for {key}; expected one of "
                    + ", ".join(sorted(valid_values))
                )
            policies[key] = value
        return policies
