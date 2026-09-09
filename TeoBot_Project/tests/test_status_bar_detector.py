import numpy as np

from game.status_bar_detector import detect_hp_mp


class FakeReader:
    def readtext(self, image, **kwargs):
        return [
            ([[110, 42], [205, 42], [205, 58], [110, 58]], "750 / 1000", 0.98),
            ([[110, 72], [205, 72], [205, 88], [110, 88]], "240 / 300", 0.97),
        ]


class FakeRapidOutput:
    boxes = np.array([
        [[100, 22], [180, 22], [180, 38], [100, 38]],
        [[330, 22], [420, 22], [420, 38], [330, 38]],
    ], dtype=np.float32)
    txts = ("2,776/2,850", "900 / 1200")
    scores = (0.99, 0.98)


class FakeRapidReader:
    def __call__(self, image):
        return FakeRapidOutput()


def test_detects_values_percentages_and_positions():
    image = np.zeros((140, 360, 3), dtype=np.uint8)
    image[38:62, 70:260] = (150, 15, 15)
    image[68:92, 70:260] = (10, 70, 180)
    result = detect_hp_mp(image, reader=FakeReader())
    assert result.hp is not None and result.mp is not None
    assert (result.hp.current, result.hp.maximum, result.hp.percent) == (750, 1000, 75.0)
    assert (result.mp.current, result.mp.maximum, result.mp.percent) == (240, 300, 80.0)


def test_horizontal_green_blue_layout_and_thousands_separators():
    image = np.zeros((90, 600, 3), dtype=np.uint8)
    image[17:43, 30:270] = (20, 175, 30)
    image[17:43, 300:550] = (30, 75, 190)
    result = detect_hp_mp(image, reader=FakeRapidReader())
    assert result.hp is not None and result.mp is not None
    assert (result.hp.current, result.hp.maximum) == (2776, 2850)
    assert round(result.hp.percent, 2) == 97.4
    assert (result.mp.current, result.mp.maximum, result.mp.percent) == (900, 1200, 75.0)
