from path_builder.models import SimilarityThresholds, SimilarityWeights
from path_builder.similarity import score_polylines


def test_identical_polylines_score_near_perfect():
    route = [(11.0, 48.0), (11.001, 48.0), (11.002, 48.001)]
    result = score_polylines(route, route, weights=SimilarityWeights(), thresholds=SimilarityThresholds())
    assert result.similarity > 99.9
    assert all(score > 99.9 for score in result.scores.values())


def test_different_polylines_score_lower_than_identical():
    reference = [(11.0, 48.0), (11.002, 48.0)]
    prediction = [(11.0, 48.0), (11.0, 48.002)]
    result = score_polylines(prediction, reference)
    assert result.similarity < 60.0
    assert result.scores["angle"] < 60.0
