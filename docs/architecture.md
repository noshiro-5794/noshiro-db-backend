# Architecture

Noshiro DB is a source-neutral anime and galgame knowledge base, personal library,
and community backend. It uses Django, Django REST Framework, PostgreSQL, Redis,
Celery, and MinIO.

## System Boundaries

```text
frontend
   |
   v
/api/v1/ (Django + DRF)
   |
   +-- PostgreSQL  knowledge, evidence, users, community
   +-- Redis       cache and Celery broker
   +-- MinIO       user-uploaded media
   `-- Celery      Bangumi/VNDB imports and AI work
```

```text
src/
  apps/          domain applications
  config/        Django, URL, and Celery configuration
  integrations/  reusable external service adapters
  shared/        framework utilities without domain ownership
```

| App | Responsibility |
| --- | --- |
| `index` | canonical entities, evidence, relations, resolution, projections |
| `sync` | provider clients, import orchestration, jobs, and Celery tasks |
| `users` | accounts, profiles, libraries, progress, reviews, collections |
| `community` | posts, comments, social graph, feeds, moderation |
| `ai` | AI runs, proposals, policies, evaluation, and audit |

Apps use the same layer meanings: `api` owns HTTP contracts, `selectors` own reads,
`services` own writes and policy, and `tasks` are thin asynchronous entry points.
External SDKs and protocols belong in `integrations`; domain apps depend on adapters,
not vendor clients.

## Knowledge Model

```text
Entity
|- Work
|  |- AnimeProfile
|  `- GalgameProfile
|- Release
|- Episode
|- Contributor (Person or Organization)
`- Character
```

`Entity` is the stable UUID, visibility, lifecycle, and redirect anchor. `Work` is a
creative work. Platform, language, regional, and limited editions are Releases;
sequels, independent seasons, OVAs, fandiscs, and materially different remakes are
separate Works. Anime and Galgame enter the primary Index collections; other works
remain searchable related entities.

Names retain language, script, region, kind, and provenance. Partial dates retain
their precision and raw value. Adult and spoiler visibility belongs to the affected
entity, description, fact, or media rather than being inferred at response time.
Core relations use typed models; `Fact` is reserved for long-tail knowledge.

## Provider Data Flow

Bangumi and VNDB are peer providers. Neither wins because it was imported first.

```text
ProviderRevision -> MappingRun -> Observation -> evidence
                                             -> resolution -> API projection
ProviderRecord <-> ProviderRepresentation <-> Entity
```

Raw revisions and normalized observations are immutable and mapper-versioned. Metrics
remain separate by provider and observation time. Resolver policy chooses rebuildable
projections without deleting conflicting source values. Merges use redirects so they
remain reversible and evidence is retained.

## AI And MCP

AI produces structured proposals and cannot write canonical tables directly.
`apps.ai` owns the durable harness, versioned Skills, typed Tools, policy, evidence,
and audit; `integrations.ai` isolates vendor clients. A run is persisted as
`AgentRun -> AgentStep -> AIRun/ToolInvocation -> SourceArtifact/AIClaim`.
The database is the execution source of truth; checkpoints are immutable snapshots,
and retries use explicit state transitions and idempotency scopes. Apply, approval,
and validation steps fail closed until a concrete handler is registered.

Provider-wide synchronization is linked to one `AgentRun` through `SyncCampaign`.
Fetch, pagination, mapping, and revision writes remain deterministic and resumable;
AI is invoked only at explicit normalization/enrichment boundaries with an
`Observation` or `SourceArtifact` attached. AI output is a claim/proposal and needs
policy review before canonical projection. `SyncWorkItem` leases make duplicate
Celery delivery and worker interruption recoverable; a campaign is not considered
complete while discovery pages or queued work items remain.

The internal MCP server exposes reads and audited proposal submission; the public
server exposes only authenticated, rate-limited safe projections. MCP tools and
in-process tools share the same namespaced, Pydantic-validated registry and explicit
permission scopes.

External HTTP clients use `OUTBOUND_PROXY_URL` when configured. Set it on servers
that cannot reach Bangumi, VNDB, image hosts, Resend, hCaptcha, or the AI provider
directly. Internal service names in `OUTBOUND_NO_PROXY_HOSTS` should remain excluded
from the proxy. On the current server, the v2raya plain HTTP inbound listens on
`192.168.3.222:7890`; use that as `OUTBOUND_PROXY_URL`.

## Public API

The only public REST root is `/api/v1/`, assembled by `config.api_urls`. There is no
unversioned compatibility API or `/api/v2/`. OpenAPI at `/api/v1/openapi/` is the
endpoint and schema contract.

The source-neutral tables currently coexist with deprecated Bangumi-centered tables
during migration. Old `Subject` data is read-only migration input. Production schema
and data changes follow [Deployment](deployment.md).
