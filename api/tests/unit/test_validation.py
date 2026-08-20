from career_intel.analysis.validation import validate_handles


def test_invented_handles_are_dropped():
    """The model may cite only from the candidate set it was given.
    Structural grounding: an invented citation cannot survive. Spec §5."""
    assert validate_handles(["e1", "e9", "e2"], {"e1", "e2"}) == ["e1", "e2"]


def test_duplicate_handles_collapse():
    assert validate_handles(["e1", "e1"], {"e1"}) == ["e1"]
