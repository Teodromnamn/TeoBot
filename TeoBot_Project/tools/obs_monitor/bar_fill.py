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
        self.sidebar_rim_rows = np.array([], dtype=int)
        if sidebar:
            hsv = cv2.cvtColor(full_image, cv2.COLOR_BGR2HSV)
            # Learn the saturated upper bevel, not the changing fill body.
            # Flat synthetic bars have no bevel and must not invent one.
            core = hsv[:, 4:-4] if hsv.shape[1] > 12 else hsv
            profile = np.median(core[:, :, 2], axis=1)
            if np.ptp(profile) >= 20:
                self.sidebar_rim_rows = np.array([y for y in range(min(2, len(profile)))
                    if np.mean((core[y, :, 1] > 90) & (core[y, :, 2] > 60)) >= .90], dtype=int)
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
            # A colored item at the fill edge can still fit a shorter contiguous
            # bar. Reject tall foreign-color objects before fitting that edge.
            # Small gold mana suffix glyphs are normal and remain allowed.
            foreign=((saturation > 90) & (value > 80) &
                     ~color_mask(image, self.resource, self.sidebar)).astype(np.uint8)
            _,_,objects,_=cv2.connectedComponentsWithStats(foreign,8)
            for x,y,w,h,area in objects[1:]:
                if (h >= max(6,image.shape[0]-4) and
                    area >= image.shape[0]*3 and
                    np.any((self.rows >= y) & (self.rows < y+h))):
                    return {'available':False,'reason':'foreign_color_overlay'}
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
            if len(self.sidebar_rim_rows):
                # Both the full rim and the native empty tail retain saturated
                # red/blue pixels. A neutral popup or an item border breaks this
                # calibrated contour even if the body resembles an empty tail.
                rim = self.sidebar_rim_rows
                native_hue = (hue >= 95) & (hue <= 135)
                if self.resource == 'hp':
                    native_hue |= (hue <= 12) | (hue >= 165)
                intact = native_hue & (saturation >= 45) & (value >= 40)
                broken = np.any(~intact[rim, 4:-4], axis=0)
                # A lower item edge can miss the upper rim entirely. Native
                # full/empty central body is shaded, never a near-black stripe.
                broken |= np.any(value[self.rows, 4:-4] < 40, axis=0)
                # Ignore isolated compression pixels; three adjoining columns
                # are enough to identify a border cutting across the bevel.
                if len(broken) >= 3 and np.any(np.convolve(broken.astype(int), np.ones(3,dtype=int), 'valid') == 3):
                    return {'available':False,'reason':'sidebar_contour_occluded'}
            neutral = ((saturation < 45) & (value > 140)).astype(np.uint8)
            _,_,objects,_ = cv2.connectedComponentsWithStats(neutral,8)
            for x,y,w,h,area in objects[1:]:
                if w >= 4 and h >= max(3,image.shape[0]//2) and area >= image.shape[0]*2:
                    return {'available':False,'reason':'neutral_overlay'}
            # Sidebar fill is always red/blue. Green/yellow item pixels are
            # foreign content, including when they hide the true fill edge.
            foreign=(hue >= 15) & (hue <= 85) & (saturation > 90) & (value > 80)
            if np.count_nonzero(foreign) >= max(4,image.shape[0]*image.shape[1]*.01):
                return {'available':False,'reason':'foreign_color_overlay'}
            # Purple/blue item icons can hide HP, and magenta icons can hide
            # mana, without containing enough green/yellow pixels. Check every
            # hue foreign to this resource. A broad component is sufficient:
            # an icon entering from above may end just before the measured rows,
            # while its neutral border still covers the actual fill edge.
            foreign=((saturation > 90) & (value > 80) &
                     ~color_mask(image,self.resource,True)).astype(np.uint8)
            if self.resource == 'hp':
                # The native empty HP tail has a blue tint. It is background,
                # not an icon; magenta/purple is outside this normal blue range.
                foreign[(hue >= 95) & (hue <= 135)]=0
            _,_,objects,_=cv2.connectedComponentsWithStats(foreign,8)
            for x,y,w,h,area in objects[1:]:
                if h >= 3 and area >= max(8,image.shape[0]*2):
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
