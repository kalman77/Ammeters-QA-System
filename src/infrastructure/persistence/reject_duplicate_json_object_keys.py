from typing import Dict, Iterable, Tuple


def reject_duplicate_json_object_keys(
    pairs: Iterable[Tuple[str, object]],
) -> Dict[str, object]:
    """Build one JSON object while rejecting duplicate member names."""
    json_object = {}
    for key, value in pairs:
        if key in json_object:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        json_object[key] = value
    return json_object
