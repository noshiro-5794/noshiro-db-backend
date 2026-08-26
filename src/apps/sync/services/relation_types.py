"""Provider relation vocabulary mapped to stable public relation slugs."""

from django.utils.text import slugify

RELATION_TYPES = {
    "seq": "sequel",
    "preq": "prequel",
    "set": "same-setting",
    "alt": "alternate-version",
    "char": "shares-characters",
    "side": "side-story",
    "par": "parent-story",
    "ser": "same-series",
    "fan": "fandisc",
    "orig": "original-version",
    "SEQUEL": "sequel",
    "PREQUEL": "prequel",
    "ADAPTATION": "adaptation",
    "ALTERNATIVE": "alternate-version",
    "SPIN_OFF": "side-story",
    "SIDE_STORY": "side-story",
    "PARENT": "parent-story",
    "CHARACTERS": "shares-characters",
    "SUMMARY": "summary",
    "FULL_STORY": "full-story",
    "OTHER": "related",
    "续作": "sequel",
    "前传": "prequel",
    "改编": "adaptation",
    "衍生": "side-story",
    "番外": "side-story",
    "总集篇": "summary",
    "相关": "related",
}


def canonical_relation_type(provider: str, raw_relation: object) -> str:
    del provider  # The raw vocabulary is intentionally shared across providers.
    raw = str(raw_relation or "").strip()
    return RELATION_TYPES.get(
        raw.upper(), RELATION_TYPES.get(raw, slugify(raw)[:128] or "related")
    )
