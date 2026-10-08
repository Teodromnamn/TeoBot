"""Offline tests for diagnostics and transactional recalibration; no Tk/OBS."""
import unittest
from monitor_dashboard import MonitorControl, recalibrate, resource_text


class DashboardTests(unittest.TestCase):
    def test_request_failure_stays_paused_until_retry(self):
        control = MonitorControl()
        control.request_calibration()
        self.assertTrue(control.paused.is_set())
        self.assertTrue(control.take_request())
        self.assertFalse(control.take_request())
        control.finish_calibration('covered')
        self.assertTrue(control.paused.is_set())
        control.request_calibration()
        self.assertTrue(control.take_request())
        control.finish_calibration()
        self.assertFalse(control.paused.is_set())

    def build(self, values, factory):
        return recalibrate('frame', 'engine', lambda f: ['new_hp', 'new_mp'],
                           lambda *a: [{'value': v} for v in values], factory, lambda v: v)

    def test_partial_bars_do_not_construct_analyzer(self):
        def forbidden(*a):
            self.fail('Partial calibration must not build an analyzer')
        with self.assertRaises(RuntimeError):
            self.build([{'current': 100, 'maximum': 210}, {'current': 240, 'maximum': 240}], forbidden)

    def test_changed_geometry_builds_fresh_analyzer_and_guards(self):
        class Analyzer:
            def __init__(self, engine, pair):
                self.pair = pair
                self.previous = None
            def calibrate(self, frame, readings, guards):
                self.guards = guards
                return {'side_rectangles': ['new_side_hp', 'new_side_mp']}
        pair, guards, analyzer, _, side = self.build(
            [{'current':210,'maximum':210}, {'current':240,'maximum':240}], Analyzer)
        self.assertEqual(pair, ['new_hp','new_mp'])
        self.assertEqual(guards, [210,240])
        self.assertIsNone(analyzer.previous)
        self.assertEqual(side['side_rectangles'][0], 'new_side_hp')

    def test_side_failure_returns_no_candidate(self):
        class Analyzer:
            def __init__(self, *a): pass
            def calibrate(self, *a): raise RuntimeError('side covered')
        with self.assertRaisesRegex(RuntimeError, 'side covered'):
            self.build([{'current':210,'maximum':210}, {'current':240,'maximum':240}], Analyzer)

    def test_invalid_resource_does_not_display_history(self):
        text, _, percent = resource_text({'valid':False, 'value':{'current':111},
            'last_known':{'value':{'current':111}}}, 1000)
        self.assertNotIn('111',text)
        self.assertEqual(percent,0)

    def test_calibration_masks_in_process_result_immediately(self):
        import test_obs_pipeline as pipeline
        old_control, old_publisher = pipeline.monitor_control, pipeline._result_publisher
        class Publisher:
            def current(self): return {'valid':True, 'hp':{'current':111}}
        try:
            pipeline._result_publisher = Publisher()
            pipeline.monitor_control = MonitorControl()
            self.assertTrue(pipeline.current_result()['valid'])
            pipeline.monitor_control.request_calibration()
            self.assertFalse(pipeline.current_result()['valid'])
            self.assertNotIn('hp', pipeline.current_result())
        finally:
            pipeline.monitor_control, pipeline._result_publisher = old_control, old_publisher

    def test_cached_side_value_slow_warning_and_occlusion(self):
        text, detail, percent = resource_text({'valid':True,'value':{'current':111},
            'effective_maximum':210,'effective_percent':111/210*100,
            'source':'side_text','maximum_is_cached':True,'observed_at_unix_ms':600,
            'text_occlusion':{'occluded':True}}, 1000)
        self.assertIn('111 / 210',text)
        self.assertIn('boczne cyfry',detail)
        self.assertIn('wolny odczyt',detail)
        self.assertIn('zasloniete',detail)
        self.assertAlmostEqual(percent,111/210*100)

if __name__ == '__main__': unittest.main()
