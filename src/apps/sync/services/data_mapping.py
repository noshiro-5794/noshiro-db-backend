def clean_string(value: object, *, max_length: int | None = None) -> str:
    if not isinstance(value, str):
        return ""

    cleaned = value.strip()
    return cleaned[:max_length] if max_length is not None else cleaned
