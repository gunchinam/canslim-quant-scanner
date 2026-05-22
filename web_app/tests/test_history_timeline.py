import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import history


def test_grade_from_score_cuts():
    assert history._grade_from_score(75) == "S"
    assert history._grade_from_score(74) == "A"
    assert history._grade_from_score(60) == "A"
    assert history._grade_from_score(59) == "B"
    assert history._grade_from_score(45) == "B"
    assert history._grade_from_score(44) == "C"


def test_grade_from_score_invalid():
    assert history._grade_from_score(None) is None
    assert history._grade_from_score("abc") is None
    assert history._grade_from_score("") is None
