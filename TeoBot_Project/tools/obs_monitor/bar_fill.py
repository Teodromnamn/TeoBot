"""Conservative calibrated fill intervals. Never converts color into exact HP."""
import cv2
import numpy as np


def color_mask(image, resource, sidebar=False):
    hue, saturation, value = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2HSV))
    if resource == 'mp':
        color = (hue >= 95) & (hue <= 135)
    elif sidebar:
        color = (hue <= 12) | (hue >= 165)
    else:
        # Top HP changes from green through yellow to red as health falls.
        color = (hue < 95) | (hue >= 165)
    return color & (saturation > 90) & (value > 60)


class FillEvidence:
    def __init__(self, full_image, resource, sidebar=False):
        self.shape = full_image.shape
        self.resource = resource
        self.sidebar = sidebar
        mask = color_mask(full_image, resource, sidebar)
        self.rows = np.flatnonzero(mask.mean(axis=1) >= .97)
        if sidebar:
            # The beveled sidebar rim remains blue even when the body is empty.
            # Only central body rows carry fill length; never fit the rim.
            height = mask.shape[0]
            self.rows = self.rows[(self.rows >= int(np.ceil(height*.4))) &
                                  (self.rows < int(np.ceil(height*.6)))]

    def measure(self, image):
        if image.shape != self.shape or not len(self.rows):
            return {'available':False, 'reason':'layout_or_calibration'}
        mask = color_mask(image, self.resource, self.sidebar)
        width = mask.shape[1]
        boundaries = []
        for row in self.rows:
            pixels = mask[row]
            prefix = np.r_[0, np.cumsum(pixels)]
            # Fit a single contiguous fill from the left; holes/tails create error.
            errors = np.arange(width+1)+prefix[-1]-2*prefix
            boundary = int(errors.argmin())
            if errors[boundary] <= max(2, width*.015):
                boundaries.append(boundary)
        if not boundaries:
            return {'available':False, 'reason':'noncontiguous_or_occluded'}
        if max(boundaries)-min(boundaries) > max(3, width*.04):
            return {'available':False, 'reason':'rows_disagree'}
        # Short sidebar bars include bevel/rounding: reserve three pixels there.
        margin = 3 if self.sidebar else 2
        return {'available':True,
                'lower_percent':100*max(0,min(boundaries)-margin)/width,
                'upper_percent':100*min(width,max(boundaries)+margin)/width,
                'support_rows':len(boundaries),
                'note':'Color consistency only; occlusion cannot always be detected.'}


def validate_fill(reading, evidence):
    result = dict(reading, fill=evidence)
    value = reading.get('value')
    if value is None:
        return result
    available = [item for item in evidence.values() if item['available']]
    percent = 100*value['current']/value['maximum'] if value.get('maximum') else None
    if percent is None or not available:
        result.update(candidate_value=value,value=None,quality='unconfirmed',fill_status='unavailable')
    elif any(not item['lower_percent'] <= percent <= item['upper_percent'] for item in available):
        result.update(candidate_value=value,value=None,quality='unconfirmed',fill_status='conflict')
    else:
        result['fill_status'] = 'consistent'
    return result
