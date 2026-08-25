# field-normalization

Normalize raw provider text into canonical taxonomy terms.

## Purpose

Converts provider-specific text labels (genres, roles, platforms, languages,
etc.) into canonical taxonomy terms. Uses deterministic NFKC normalization
first, then AI-assisted mapping when no reviewed alias exists.

## Input

| Field | Type | Description |
|-------|------|-------------|
| vocabulary | string | Taxonomy vocabulary slug (e.g. genre, role, platform) |
| source_text | string | Raw provider text to normalize |
| provider_namespace | string | Provider namespace (e.g. bangumi, vndb, anilist) |
| language | string | Source language code |
| context | object | Optional: entity type, related terms |

## Output

| Field | Type | Description |
|-------|------|-------------|
| action | enum | map_existing, propose_new, preserve_raw, abstain |
| normalized_key | string | NFKC-normalized, whitespace-collapsed key |
| preferred_term | string | Preferred term in target language |
| language | string | Detected language code |
| script | string | ISO 15924 script code |
| confidence | number | 0-1 model confidence |
| reason | string | Concise explanation |

## Actions

- **map_existing**: Text matches a reviewed TermAlias or taxonomy Term.
- **propose_new**: New term needed; includes proposed_labels for multi-language.
- **preserve_raw**: Text is an identifier/title; keep as-is.
- **abstain**: Not enough information to decide.

## Policy

- Shadow mode by default; no auto-apply to canonical data.
- Confidence >= 0.95 required for auto-apply (when enabled).
- New term proposals always require admin review.
- Legacy TermAlias entries must be audited before auto-apply.

## Model

- Fast model (DeepSeek V4 Flash) for initial classification.
- Fallback to reasoning model (DeepSeek V4 Pro) if confidence < 0.85.

## Version

- Skill: 1.0.0
- Schema: 1.0.0
- Prompt: field-normalization-v1
