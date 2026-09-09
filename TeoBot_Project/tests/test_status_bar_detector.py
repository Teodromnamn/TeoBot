import numpy as np

from game.status_bar_detector import detect_hp_mp


class FakeReader:
    def readtext(self, image, **kwargs):
        return [
            ([[110, 42], [205, 42], [205, 58], [110, 58]], "750 / 1000", 0.98),
            ([[110, 72], [205, 72], [205, 88], [110, 88]], "240 / 300", 0.97),
        ]


def test_detects_values_percentages_and_positions():
    image = np.zeros((140, 360, 3), dtype=np.uint8)
    image[38:62, 70:260] = (150, 15, 15)
    image[68:92, 70:260] = (10, 70, 180)
    result = detect_hp_mp(image, reader=FakeReader())
    assert result.hp is not None and result.mp is not None
    assert (result.hp.current, result.hp.maximum, result.hp.percent) == (750, 1000, 75.0)
    assert (result.mp.current, result.mp.maximum, result.mp.percent) == (240, 300, 80.0)

