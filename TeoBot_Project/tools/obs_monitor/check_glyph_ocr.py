import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import cv2
import numpy as np
from glyph_ocr import read_digits,is_slash,recover_ratio
from dual_source import recognize_side


class Tests(unittest.TestCase):
    def image(self):
        image=np.full((30,50),255,np.uint8)
        for x in (5,20,35):image[5:25,x:x+3]=0
        return image

    def test_repeated_digits_recovered_without_top_hint(self):
        e=Mock();e.recognize.return_value=SimpleNamespace(txts=['1'])
        self.assertEqual(read_digits(e,self.image())['text'],'111')
        crop=np.repeat((255-self.image())[:,:,None],3,axis=2)
        self.assertIsNone(recognize_side(e,crop)['current'])
        r=recognize_side(e,crop,glyph_retry=True)
        self.assertEqual(r['current'],111)
        self.assertEqual(r['raw'],'1')

    def test_colored_item_edges_cannot_be_recovered_as_digits(self):
        crop=np.repeat((255-self.image())[:,:,None],3,axis=2)
        crop[6:12,5:9]=[10,180,220]
        e=Mock();e.recognize.return_value=SimpleNamespace(txts=['1'])
        r=recognize_side(e,crop,glyph_retry=True)
        self.assertIsNone(r['current'])
        self.assertEqual(r['reason'],'foreign_color_overlay')
        e.recognize.assert_called_once()

    def test_disagreement_or_multiple_characters_rejected(self):
        e=Mock();e.recognize.side_effect=[SimpleNamespace(txts=['1']),SimpleNamespace(txts=['7'])]
        self.assertIsNone(read_digits(e,self.image())['text'])
        e=Mock();e.recognize.return_value=SimpleNamespace(txts=['11'])
        self.assertIsNone(read_digits(e,self.image())['text'])

    def test_ratio_recovery_uses_visible_slash_and_preserves_both_numbers(self):
        image=np.full((30,80),255,np.uint8)
        for x in (3,15,52,66):image[4:26,x:x+3]=0
        cv2.line(image,(43,2),(29,27),0,2)
        e=Mock()
        e.recognize.side_effect=lambda image,psm:SimpleNamespace(txts=['1' if psm==10 else '11'])
        self.assertEqual(recover_ratio(e,image)['text'],'11/11')

    def test_separator_is_required_visually(self):
        e=Mock()
        self.assertIsNone(recover_ratio(e,self.image())['text'])
        e.recognize.assert_not_called()
        slash=np.full((30,20),255,np.uint8)
        cv2.line(slash,(17,1),(2,28),0,2)
        self.assertTrue(is_slash(slash))
        self.assertFalse(is_slash(self.image()[:,5:8]))


if __name__=='__main__':unittest.main()
