from collections.abc import Collection, Sequence


def validate_handles(returned: Sequence[str], allowed: Collection[str]) -> list[str]:
    """Filter and deduplicate handles against an allowed set.

    Returns only handles from returned that are present in allowed,
    preserving original order with duplicates collapsed (each handle
    appears at most once in the output).

    This enforces structural grounding: the model may cite only from
    the candidate set it was given. Invented citations are dropped.

    Args:
        returned: Sequence of handles returned by the model
        allowed: Collection of allowed/valid handles

    Returns:
        Filtered, deduplicated list of valid handles in original order
    """
    seen = set()
    result = []

    for handle in returned:
        if handle in allowed and handle not in seen:
            result.append(handle)
            seen.add(handle)

    return result
