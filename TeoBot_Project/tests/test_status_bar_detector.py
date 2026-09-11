import numpy as np
import cv2
import pytest

from game.status_bar_detector import detect_hp_mp_legacy as detect_hp_mp, _Candidate, _select, _find_bar_rect


@pytest.mark.parametrize("mana", ["60/60", "10/60", "unreadable"])
def test_tibia_calibration_requires_both_full(mana):
    from game.status_bar_detector import detect_hp_mp as calibrate
    image = np.zeros((720, 1280, 3), np.uint8)
    image[4:14, 120:570] = (0, 180, 0)
    image[4:14, 578:1028] = (0, 70, 180)
    class Reader:
        calls = 0
        def readtext(self, image, **kwargs):
            self.calls += 1
            return [([[0,0],[100,0],[100,20],[0,20]], "155/155" if self.calls == 1 else mana, .99)]
    result = calibrate(image, reader=Reader())
    if mana == "60/60":
        assert result.hp.current == 155 and result.mp.current == 60
        assert result.hp.rect == (120, 4, 450, 10)
    else:
        assert result.hp is None and result.mp is None


@pytest.mark.parametrize("fraction", [0, .1, .5, 1])
def test_complete_frame_includes_empty_area_and_text(fraction):
    image = np.zeros((140, 600, 3), dtype=np.uint8)
    for y, colour in [(30, (10, 180, 20)), (75, (10, 40, 180))]:
        image[y:y+26, 50:450] = (65, 65, 65)
        image[y:y+26, 50:50+int(400*fraction)] = colour
        cv2.rectangle(image, (49, y-1), (450, y+26), (200, 200, 200), 1)
        cv2.putText(image, f"{int(100*fraction)}/100", (210, y+18),
                    cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
        rect = _find_bar_rect(image, (210, y+5, 60, 16), fraction)
        assert abs(rect[0]-49) <= 3
        assert 398 <= rect[2] <= 406
        assert rect[1] <= y+1 and rect[1]+rect[3] >= y+25
        assert rect[3] <= 32


def test_overlapping_rectangles_cannot_be_selected_as_pair():
    a = _Candidate(100, 100, "100/100", .99, (40, 10, 60, 15), (0, 0, 400, 50), .4, .3)
    b = _Candidate(50, 100, "50/100", .99, (200, 10, 60, 15), (0, 0, 400, 50), .4, .3)
    hp, mp = _select([a, b])
    assert hp is None or mp is None


def test_background_and_adjacent_colours_do_not_join_bars():
    image = np.full((160, 900, 3), (80, 130, 45), dtype=np.uint8)
    image[30:54, 60:300] = (180, 10, 10)
    image[58:82, 60:300] = (10, 40, 190)
    hp = _find_bar_rect(image, (130, 34, 80, 16), 1)
    mp = _find_bar_rect(image, (130, 62, 80, 16), .6)
    assert 230 <= hp[2] <= 250
    assert 230 <= mp[2] <= 250
    assert hp[1]+hp[3] <= mp[1]


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
    assert result.hp.rect[2] >= 180
    assert result.mp.rect[2] >= 180


def test_horizontal_green_blue_layout_and_thousands_separators():
    image = np.zeros((90, 600, 3), dtype=np.uint8)
    image[17:43, 30:270] = (20, 175, 30)
    image[17:43, 300:550] = (30, 75, 190)
    result = detect_hp_mp(image, reader=FakeRapidReader())
    assert result.hp is not None and result.mp is not None
    assert (result.hp.current, result.hp.maximum) == (2776, 2850)
    assert round(result.hp.percent, 2) == 97.4
    assert (result.mp.current, result.mp.maximum, result.mp.percent) == (900, 1200, 75.0)


class MultiplePairsReader:
    def readtext(self, image, **kwargs):
        return [
            ([[170, 32], [230, 32], [230, 46], [170, 46]], "900/1000", 0.98),
            ([[170, 62], [230, 62], [230, 76], [170, 76]], "300/400", 0.98),
            ([[485, 25], [535, 25], [535, 37], [485, 37]], "90/100", 0.99),
            ([[485, 45], [535, 45], [535, 57], [485, 57]], "30/40", 0.99),
        ]


def test_selects_largest_valid_pair_instead_of_party_bars():
    image = np.zeros((120, 650, 3), dtype=np.uint8)
    image[25:52, 60:340] = (170, 20, 20)
    image[55:82, 60:340] = (20, 70, 190)
    image[20:41, 450:570] = (20, 165, 30)
    image[42:63, 450:570] = (20, 70, 180)
    result = detect_hp_mp(image, reader=MultiplePairsReader())
    assert result.hp is not None and result.mp is not None
    assert (result.hp.current, result.hp.maximum) == (900, 1000)
    assert (result.mp.current, result.mp.maximum) == (300, 400)
    assert result.hp.rect[2] > 200
    assert result.mp.rect[2] > 200
