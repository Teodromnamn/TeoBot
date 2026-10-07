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
        hue,saturation,value=cv2.split(cv2.cvtColor(image,cv2.COLOR_BGR2HSV))
        if not self.sidebar:
            # A gray tooltip can look like a perfectly contiguous empty tail.
            # Broad bright neutral content is foreign to the dark bar background;
            # narrow white counter glyphs must not trigger this rejection.
            neutral_full=((saturation < 80) & (value > 100)).astype(np.uint8)
            neutral_full[:2]=0;neutral_full[-2:]=0
            count,_,stats,_=cv2.connectedComponentsWithStats(neutral_full,8)
            for x,y,w,h,area in stats[1:]:
                if h >= max(6,image.shape[0]-4) and w >= 4 and area >= image.shape[0]*3:
                    return {'available':False,'reason':'neutral_overlay'}
            neutral=(saturation[self.rows] < 45) & (value[self.rows] > 125)
            if np.count_nonzero(neutral) > neutral.size*.10:
                return {'available':False,'reason':'neutral_overlay'}
        if self.sidebar:
            hue,saturation,value=cv2.split(cv2.cvtColor(image,cv2.COLOR_BGR2HSV))
            # Sidebar fill is always red/blue. Green/yellow item pixels are
            # foreign content, including when they hide the true fill edge.
            foreign=(hue >= 15) & (hue <= 85) & (saturation > 90) & (value > 80)
            if np.count_nonzero(foreign) >= max(4,image.shape[0]*image.shape[1]*.01):
                return {'available':False,'reason':'foreign_color_overlay'}
        mask = color_mask(image, self.resource, self.sidebar)
        width = mask.shape[1]
        boundaries = []
        for row in self.rows:
            pixels = mask[row]
            # Top mana fills from the right; sidebar mana fills from the left.
            if self.resource == 'mp' and not self.sidebar:
                pixels = pixels[::-1]
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
        margin = (3 if self.sidebar else 2) + .5
        if self.resource == 'mp' and not self.sidebar:
            # Saturation at the shaded top mana edge changes its visible extent.
            margin = max(margin,width*.02)
        return {'available':True,
                'lower_percent':100*max(0,min(boundaries)-margin)/width,
                'upper_percent':100*min(width,max(boundaries)+margin)/width,
                'support_rows':len(boundaries),
                'pixel_rounding_margin':.5,
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
