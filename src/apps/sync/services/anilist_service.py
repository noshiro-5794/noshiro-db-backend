from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils.text import slugify

from apps.index.models import (
    AiringEvent,
    AnimeProfile,
    Appearance,
    Contributor,
    Credit,
    Entity,
    EntityDescription,
    EntityName,
    EntityRelation,
    EntityRelationEvidence,
    EntityTerm,
    ExternalLink,
    IndexCollection,
    IndexMembership,
    Organization,
    Person,
    ProviderRecord,
    ProviderRepresentation,
    Taxonomy,
    Term,
    TermLabel,
    TermMapping,
    VoicePerformance,
    Work,
)
from apps.index.services import (
    entity_resolution_service,
    knowledge_ingestion_service,
)
from apps.sync.providers.anilist import (
    ANILIST_ANIME_NAMESPACE,
    ANILIST_CALENDAR_NAMESPACE,
    ANILIST_CHARACTER_NAMESPACE,
    ANILIST_EPISODE_NAMESPACE,
    ANILIST_GENRE_NAMESPACE,
    ANILIST_STAFF_NAMESPACE,
    ANILIST_STUDIO_NAMESPACE,
    ANILIST_TAG_NAMESPACE,
    anilist_client,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.relation_types import canonical_relation_type
from apps.sync.services.source_record_service import source_record_service


class AniListImportService:
    @staticmethod
    def _as_int(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    @staticmethod
    def _as_date(value: dict[str, Any] | None) -> str | None:
        if not isinstance(value, dict):
            return None
        year = value.get("year")
        month = value.get("month")
        day = value.get("day")
        if not isinstance(year, int) or not isinstance(month, int):
            return None
        if not isinstance(day, int):
            day = 1
        try:
            return datetime(year, month, day, tzinfo=UTC).date().isoformat()
        except ValueError:
            return None

    @staticmethod
    def _audience(media: dict[str, Any]) -> str:
        return (
            Entity.Audience.ADULT
            if media.get("isAdult") is True
            else Entity.Audience.GENERAL
        )

    def import_media(self, anilist_id: int) -> Entity:
        if (
            not isinstance(anilist_id, int)
            or isinstance(anilist_id, bool)
            or anilist_id <= 0
        ):
            raise ValueError("AniList media IDs must be positive integers.")
        media = anilist_client.fetch_media(anilist_id)
        return self._persist_media(media)

    @transaction.atomic
    def _persist_media(self, media: dict[str, Any]) -> Entity:
        external_id = str(media["id"])
        recorded = source_record_service.record(
            namespace_spec=ANILIST_ANIME_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=external_id,
                payload=media,
                canonical_url=media.get("siteUrl")
                or f"https://anilist.co/anime/{external_id}",
                schema_version="anilist-graphql",
                mapper_version="anilist-media-v1",
                upstream_updated_at=self._updated_at(media),
            ),
        )
        observation = knowledge_ingestion_service.record_observation(
            provider_record=recorded.record,
            mapper="anilist.media",
            mapper_version="anilist-media-v1",
            normalized_data=media,
            schema_name="index.work",
            schema_version="1",
        )
        entity = self._resolve_work_entity(recorded.record, media)
        work, _ = Work.objects.update_or_create(
            entity=entity,
            defaults={"work_type": Work.WorkType.ANIME},
        )
        AnimeProfile.objects.update_or_create(
            work=work,
            defaults={
                "format": media.get("format") or "",
                "source_material": media.get("source") or "",
                "episode_count": self._as_int(media.get("episodes")),
            },
        )
        knowledge_ingestion_service._upsert_provider_representation(
            provider_record=recorded.record,
            entity=entity,
            representation_method=ProviderRepresentation.Method.PROVIDER,
        )
        self._upsert_names(
            entity=entity,
            record=recorded.record,
            observation=observation,
            media=media,
        )
        self._upsert_description(
            entity=entity,
            record=recorded.record,
            observation=observation,
            media=media,
        )
        self._upsert_media(
            entity=entity,
            record=recorded.record,
            observation=observation,
            media=media,
        )
        self._upsert_external_links(
            entity=entity,
            record=recorded.record,
            observation=observation,
            media=media,
        )
        self._upsert_work_facts(entity=entity, observation=observation, media=media)
        self._ensure_anime_membership(entity)
        self._upsert_genres_and_tags(
            entity=entity, observation=observation, media=media
        )
        self._import_relations(entity=entity, observation=observation, media=media)
        self._import_characters(work=work, observation=observation, media=media)
        self._import_staff(work=work, observation=observation, media=media)
        self._import_studios(work=work, observation=observation, media=media)
        self._import_airing_schedule(
            entity=entity,
            media=media,
            work=work,
        )
        return entity_resolution_service.resolve(entity)

    @staticmethod
    def _updated_at(media: dict[str, Any]):
        value = media.get("updatedAt")
        if isinstance(value, int) and value > 0:
            return datetime.fromtimestamp(value, tz=UTC)
        return None

    def _resolve_work_entity(
        self,
        record: ProviderRecord,
        media: dict[str, Any],
    ) -> Entity:
        return knowledge_ingestion_service._resolve_or_create_entity(
            provider_record=record,
            kind=Entity.Kind.WORK,
            audience=self._audience(media),
        )

    @staticmethod
    def _upsert_names(*, entity, record, observation, media) -> None:
        title = media.get("title") or {}
        names: list[EntityName] = []
        for key, kind in (
            ("romaji", EntityName.Kind.ROMANIZED),
            ("english", EntityName.Kind.OFFICIAL),
            ("native", EntityName.Kind.ORIGINAL),
            ("userPreferred", EntityName.Kind.OFFICIAL),
        ):
            value = title.get(key)
            if isinstance(value, str) and value:
                names.append(
                    EntityName(
                        entity=entity,
                        provider_record=record,
                        observation=observation,
                        text=value[:256],
                        language="ja" if key in {"native", "romaji"} else "en",
                        script="Jpan" if key == "native" else "Latn",
                        kind=kind,
                        is_official=True,
                    )
                )
        for synonym in media.get("synonyms") or []:
            if isinstance(synonym, str) and synonym:
                names.append(
                    EntityName(
                        entity=entity,
                        provider_record=record,
                        observation=observation,
                        text=synonym[:256],
                        language="",
                        kind=EntityName.Kind.ALIAS,
                    )
                )
        EntityName.objects.bulk_create(names, ignore_conflicts=True)

    @staticmethod
    def _upsert_description(*, entity, record, observation, media) -> None:
        description = media.get("description")
        if not isinstance(description, str) or not description.strip():
            return
        EntityDescription.objects.update_or_create(
            entity=entity,
            language="",
            provider_record=record,
            observation=observation,
            defaults={"text": description},
        )

    @staticmethod
    def _upsert_media(*, entity, record, observation, media) -> None:
        cover = media.get("coverImage") or {}
        for purpose, key in (("poster", "large"), ("thumbnail", "medium")):
            url = cover.get(key)
            if isinstance(url, str) and url:
                knowledge_ingestion_service._upsert_media(
                    entity=entity,
                    provider_record=record,
                    observation=observation,
                    original=url if purpose == "poster" else "",
                    thumbnail=url if purpose == "thumbnail" else "",
                )
        banner = media.get("bannerImage")
        if isinstance(banner, str) and banner:
            knowledge_ingestion_service._upsert_media(
                entity=entity,
                provider_record=record,
                observation=observation,
                original=banner,
                thumbnail="",
            )

    @staticmethod
    def _upsert_external_links(*, entity, record, observation, media) -> None:
        links = [{"url": media.get("siteUrl"), "label": "AniList"}]
        links.extend(media.get("externalLinks") or [])
        for item in links:
            url = item.get("url") if isinstance(item, dict) else item
            if not isinstance(url, str) or not url:
                continue
            label = (item.get("site") or "") if isinstance(item, dict) else ""
            ExternalLink.objects.get_or_create(
                entity=entity,
                url=url,
                provider_record=record,
                observation=observation,
                defaults={"label": label[:128], "link_type": slugify(label)[:64]},
            )

    def _upsert_work_facts(self, *, entity, observation, media) -> None:
        candidates = {
            "anilist-status": media.get("status"),
            "anilist-season": media.get("season"),
            "anilist-season-year": media.get("seasonYear"),
            "episode-count": self._as_int(media.get("episodes")),
            "duration-minutes": self._as_int(media.get("duration")),
            "anilist-source": media.get("source"),
            "release-date": self._as_date(media.get("startDate")),
            "end-date": self._as_date(media.get("endDate")),
            "anilist-id-mal": self._as_int(media.get("idMal")),
            "anilist-average-score": media.get("averageScore"),
            "anilist-popularity": media.get("popularity"),
            "anilist-favourites": media.get("favourites"),
            "anilist-trending": media.get("trending"),
        }
        for slug, value in candidates.items():
            if value is None or value == "":
                continue
            value_type = "date" if slug in {"release-date", "end-date"} else "string"
            if isinstance(value, bool):
                value_type = "boolean"
            elif isinstance(value, (int, Decimal)):
                value_type = "number"
            knowledge_ingestion_service.record_fact(
                entity=entity,
                observation=observation,
                slug=slug,
                name=slug.replace("-", " ").title(),
                value=value,
                value_type=value_type,
                json_pointer=f"/{slugify(slug)}",
            )

    @staticmethod
    def _ensure_anime_membership(entity: Entity) -> None:
        collection, _ = IndexCollection.objects.get_or_create(
            slug="anime",
            defaults={"name": "Anime"},
        )
        IndexMembership.objects.update_or_create(
            collection=collection,
            entity=entity,
            defaults={
                "listing_state": IndexMembership.State.LISTED,
                "inclusion_reason": "AniList anime",
            },
        )

    def _upsert_genres_and_tags(self, *, entity, observation, media) -> None:
        for namespace_spec, taxonomy_slug, taxonomy_name, values in (
            (
                ANILIST_GENRE_NAMESPACE,
                "anilist-genres",
                "AniList Genres",
                media.get("genres") or [],
            ),
            (
                ANILIST_TAG_NAMESPACE,
                "anilist-tags",
                "AniList Tags",
                [
                    item.get("name")
                    for item in (media.get("tags") or [])
                    if isinstance(item, dict)
                ],
            ),
        ):
            taxonomy, _ = Taxonomy.objects.get_or_create(
                slug=taxonomy_slug,
                defaults={"name": taxonomy_name},
            )
            for name in values:
                if not isinstance(name, str) or not name:
                    continue
                record = source_record_service.ensure_record(
                    namespace_spec=namespace_spec,
                    external_id=slugify(name),
                    origin=ProviderRecord.Origin.API,
                    canonical_url=f"https://anilist.co/search/anime?{slugify(name)}",
                )
                term, _ = Term.objects.update_or_create(
                    taxonomy=taxonomy,
                    slug=slugify(name),
                )
                TermLabel.objects.get_or_create(
                    term=term,
                    language="en",
                    script="Latn",
                    text=name,
                    defaults={"is_preferred": True},
                )
                TermMapping.objects.get_or_create(term=term, provider_record=record)
                EntityTerm.objects.get_or_create(
                    entity=entity,
                    term=term,
                    observation=observation,
                )

    def _import_relations(self, *, entity, observation, media) -> None:
        relations = media.get("relations") or {}
        for index, edge in enumerate(
            relations.get("edges") or [] if isinstance(relations, dict) else relations
        ):
            if not isinstance(edge, dict):
                continue
            node = edge.get("node") or {}
            raw_relation = edge.get("relationType")
            if not isinstance(raw_relation, str) or not isinstance(node, dict):
                continue
            target = self._ensure_related_entity(node)
            if target is None:
                continue
            relation, _ = EntityRelation.objects.get_or_create(
                from_entity=entity,
                to_entity=target,
                relation_type=canonical_relation_type("anilist", raw_relation),
            )
            EntityRelationEvidence.objects.get_or_create(
                relation=relation,
                observation=observation,
                json_pointer=f"/relations/edges/{index}",
                defaults={"raw_relation": raw_relation[:256]},
            )

    def _ensure_related_entity(self, node: dict[str, Any]) -> Entity | None:
        anilist_id = node.get("id")
        if not isinstance(anilist_id, int):
            return None
        external_id = str(anilist_id)
        record = source_record_service.ensure_record(
            namespace_spec=ANILIST_ANIME_NAMESPACE,
            external_id=external_id,
            origin=ProviderRecord.Origin.API,
            canonical_url=f"https://anilist.co/anime/{external_id}",
        )
        entity = knowledge_ingestion_service._resolve_or_create_entity(
            provider_record=record,
            kind=Entity.Kind.WORK,
            audience=Entity.Audience.UNKNOWN,
        )
        knowledge_ingestion_service._upsert_provider_representation(
            provider_record=record,
            entity=entity,
            representation_method=ProviderRepresentation.Method.PROVIDER,
        )
        Work.objects.get_or_create(
            entity=entity,
            defaults={"work_type": self._work_type_from_format(node.get("format"))},
        )
        title = node.get("title") or {}
        name = title.get("romaji") or title.get("english") or title.get("native")
        if isinstance(name, str) and name:
            EntityName.objects.get_or_create(
                entity=entity,
                provider_record=record,
                text=name[:256],
                kind=EntityName.Kind.OFFICIAL,
            )
        return entity

    @staticmethod
    def _work_type_from_format(format_: Any) -> str:
        if format_ in {
            "TV",
            "TV_SHORT",
            "MOVIE",
            "OVA",
            "ONA",
            "SPECIAL",
            "MUSIC",
        }:
            return Work.WorkType.ANIME
        return Work.WorkType.OTHER

    def _import_characters(self, *, work, observation, media) -> None:
        characters = media.get("characters") or {}
        for edge in (
            characters.get("edges") or []
            if isinstance(characters, dict)
            else characters
        ):
            if not isinstance(edge, dict):
                continue
            node = edge.get("node") or {}
            role = edge.get("role") or ""
            character = self._ensure_character(node)
            if character is None:
                continue
            appearance, _ = Appearance.objects.get_or_create(
                work=work,
                character_entity=character,
                role=role,
                observation=observation,
            )
            for actor in edge.get("voiceActors") or []:
                if not isinstance(actor, dict):
                    continue
                contributor = self._ensure_person(actor)
                if contributor is None:
                    continue
                VoicePerformance.objects.get_or_create(
                    appearance=appearance,
                    contributor=contributor,
                    observation=observation,
                )

    def _ensure_character(self, node: dict[str, Any]) -> Entity | None:
        anilist_id = node.get("id")
        if not isinstance(anilist_id, int):
            return None
        record = source_record_service.ensure_record(
            namespace_spec=ANILIST_CHARACTER_NAMESPACE,
            external_id=str(anilist_id),
            origin=ProviderRecord.Origin.API,
            canonical_url=f"https://anilist.co/character/{anilist_id}",
        )
        entity = knowledge_ingestion_service._resolve_or_create_entity(
            provider_record=record,
            kind=Entity.Kind.CHARACTER,
            audience=Entity.Audience.UNKNOWN,
        )
        knowledge_ingestion_service._upsert_provider_representation(
            provider_record=record,
            entity=entity,
            representation_method=ProviderRepresentation.Method.PROVIDER,
        )
        name = node.get("name") or {}
        full_name = name.get("full") or name.get("native")
        if isinstance(full_name, str) and full_name:
            EntityName.objects.get_or_create(
                entity=entity,
                provider_record=record,
                text=full_name[:256],
                kind=EntityName.Kind.OFFICIAL,
            )
        return entity

    def _import_staff(self, *, work, observation, media) -> None:
        staff = media.get("staff") or {}
        for edge in staff.get("edges") or [] if isinstance(staff, dict) else staff:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node") or {}
            role = edge.get("role") or ""
            contributor = self._ensure_person(node)
            if contributor is None:
                continue
            Credit.objects.get_or_create(
                work=work,
                contributor=contributor,
                role=role,
                observation=observation,
            )

    def _import_studios(self, *, work, observation, media) -> None:
        studios = media.get("studios") or {}
        for edge in (
            studios.get("edges") or [] if isinstance(studios, dict) else studios
        ):
            if not isinstance(edge, dict):
                continue
            node = edge.get("node") or {}
            contributor = self._ensure_organization(node)
            if contributor is None:
                continue
            Credit.objects.get_or_create(
                work=work,
                contributor=contributor,
                role="Studio",
                observation=observation,
            )

    def _ensure_person(self, node: dict[str, Any]) -> Contributor | None:
        anilist_id = node.get("id")
        if not isinstance(anilist_id, int):
            return None
        record = source_record_service.ensure_record(
            namespace_spec=ANILIST_STAFF_NAMESPACE,
            external_id=str(anilist_id),
            origin=ProviderRecord.Origin.API,
            canonical_url=f"https://anilist.co/staff/{anilist_id}",
        )
        entity = knowledge_ingestion_service._resolve_or_create_entity(
            provider_record=record,
            kind=Entity.Kind.CONTRIBUTOR,
            audience=Entity.Audience.UNKNOWN,
        )
        knowledge_ingestion_service._upsert_provider_representation(
            provider_record=record,
            entity=entity,
            representation_method=ProviderRepresentation.Method.PROVIDER,
        )
        contributor, _ = Contributor.objects.update_or_create(
            entity=entity,
            defaults={"kind": Contributor.Kind.PERSON},
        )
        Person.objects.get_or_create(contributor=contributor)
        name = node.get("name") or {}
        full_name = name.get("full") or name.get("native")
        if isinstance(full_name, str) and full_name:
            EntityName.objects.get_or_create(
                entity=entity,
                provider_record=record,
                text=full_name[:256],
                kind=EntityName.Kind.OFFICIAL,
            )
        return contributor

    def _ensure_organization(self, node: dict[str, Any]) -> Contributor | None:
        anilist_id = node.get("id")
        if not isinstance(anilist_id, int):
            return None
        record = source_record_service.ensure_record(
            namespace_spec=ANILIST_STUDIO_NAMESPACE,
            external_id=str(anilist_id),
            origin=ProviderRecord.Origin.API,
            canonical_url=f"https://anilist.co/studio/{anilist_id}",
        )
        entity = knowledge_ingestion_service._resolve_or_create_entity(
            provider_record=record,
            kind=Entity.Kind.CONTRIBUTOR,
            audience=Entity.Audience.UNKNOWN,
        )
        knowledge_ingestion_service._upsert_provider_representation(
            provider_record=record,
            entity=entity,
            representation_method=ProviderRepresentation.Method.PROVIDER,
        )
        contributor, _ = Contributor.objects.update_or_create(
            entity=entity,
            defaults={"kind": Contributor.Kind.ORGANIZATION},
        )
        Organization.objects.get_or_create(contributor=contributor)
        name = node.get("name")
        if isinstance(name, str) and name:
            EntityName.objects.get_or_create(
                entity=entity,
                provider_record=record,
                text=name[:256],
                kind=EntityName.Kind.OFFICIAL,
            )
        return contributor

    def _import_airing_schedule(self, *, entity, media, work) -> None:
        schedule = media.get("airingSchedule") or {}
        nodes = schedule.get("nodes") or []
        if not isinstance(nodes, list) or not nodes:
            return
        calendar_recorded = source_record_service.record(
            namespace_spec=ANILIST_CALENDAR_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=str(media["id"]),
                payload={"media": media, "schedule": nodes},
                canonical_url=f"https://anilist.co/anime/{media['id']}",
                schema_version="anilist-graphql",
                mapper_version="anilist-airing-v1",
            ),
        )
        calendar_observation = knowledge_ingestion_service.record_observation(
            provider_record=calendar_recorded.record,
            mapper="anilist.airing",
            mapper_version="anilist-airing-v1",
            normalized_data={"media": media, "schedule": nodes},
            schema_name="index.schedule",
            schema_version="1",
        )
        events: list[AiringEvent] = []
        for index, item in enumerate(nodes):
            if not isinstance(item, dict):
                continue
            airing_at = self._as_int(item.get("airingAt"))
            if airing_at is None:
                continue
            starts_at = datetime.fromtimestamp(airing_at, tz=UTC)
            episode_number = self._as_int(item.get("episode"))
            episode_entity = self._upsert_episode(
                parent_entity=entity,
                item=item,
                starts_at=starts_at,
                calendar_observation=calendar_observation,
                json_pointer=f"/schedule/{index}",
            )
            events.append(
                AiringEvent(
                    work=work,
                    episode_entity=episode_entity,
                    starts_at=starts_at,
                    timezone="UTC",
                    region="",
                    weekday=starts_at.isoweekday(),
                    precision=AiringEvent.Precision.MINUTE,
                    raw_value=starts_at.isoformat(),
                    observation=calendar_observation,
                )
            )
            if episode_number is not None:
                knowledge_ingestion_service.record_fact(
                    entity=episode_entity,
                    observation=calendar_observation,
                    slug="episode-number",
                    name="Episode Number",
                    value=str(episode_number),
                    value_type="string",
                    json_pointer=f"/schedule/{index}/episode",
                )
        AiringEvent.objects.bulk_create(events, ignore_conflicts=True)

    def _upsert_episode(
        self,
        *,
        parent_entity: Entity,
        item: dict[str, Any],
        starts_at: datetime,
        calendar_observation,
        json_pointer: str,
    ) -> Entity:
        episode_number = self._as_int(item.get("episode"))
        external_id = item.get("id") or item.get("episode") or starts_at.isoformat()
        recorded = source_record_service.record(
            namespace_spec=ANILIST_EPISODE_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=str(external_id),
                payload=item,
                canonical_url=f"https://anilist.co/anime/{parent_entity.id}",
                schema_version="anilist-graphql",
                mapper_version="anilist-episode-v1",
            ),
        )
        observation = knowledge_ingestion_service.record_observation(
            provider_record=recorded.record,
            mapper="anilist.episode",
            mapper_version="anilist-episode-v1",
            normalized_data=item,
            schema_name="index.episode",
            schema_version="1",
        )
        entity = knowledge_ingestion_service._resolve_or_create_entity(
            provider_record=recorded.record,
            kind=Entity.Kind.EPISODE,
            audience=parent_entity.audience,
        )
        knowledge_ingestion_service._upsert_provider_representation(
            provider_record=recorded.record,
            entity=entity,
            representation_method=ProviderRepresentation.Method.PROVIDER,
        )
        if episode_number is not None:
            EntityName.objects.get_or_create(
                entity=entity,
                provider_record=recorded.record,
                observation=observation,
                text=f"Episode {episode_number}",
                language="en",
                kind=EntityName.Kind.OFFICIAL,
            )
        relation, _ = EntityRelation.objects.get_or_create(
            from_entity=parent_entity,
            to_entity=entity,
            relation_type="has-episode",
        )
        EntityRelationEvidence.objects.get_or_create(
            relation=relation,
            observation=calendar_observation,
            json_pointer=json_pointer,
            defaults={"raw_relation": "has-episode"},
        )
        return entity


anilist_import_service = AniListImportService()
