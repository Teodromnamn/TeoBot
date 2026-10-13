"""Evaluate a below-threshold rule without inventing an exact OCR value.

Only evaluates observations. Sending keys, cooldowns and healing are separate.
"""
import math
import time


def below_threshold(resource, threshold, unit='current', now_ms=None):
    if unit not in ('current','percent'):
        raise ValueError('unit must be current or percent')
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError('threshold must be finite and nonnegative')
    now_ms=time.time_ns()//1000000 if now_ms is None else now_ms
    if resource.get('expires_at_unix_ms',0) <= now_ms:
        return {'decision':'unavailable','reason':'expired_or_missing'}
    if resource.get('valid') and resource.get('value') is not None:
        value=resource['value']
        number=value.get('current') if unit=='current' else resource.get('effective_percent')
        if number is None:
            return {'decision':'unavailable','reason':'missing_percentage'}
        lower=upper=number
    elif resource.get('range_valid') and resource.get('value_range'):
        interval=resource['value_range']
        lower=interval.get('lower' if unit=='current' else 'lower_percent')
        upper=interval.get('upper' if unit=='current' else 'upper_percent')
    else:
        return {'decision':'unavailable','reason':'unconfirmed_or_unreadable'}
    if (lower is None or upper is None or not math.isfinite(lower)
            or not math.isfinite(upper) or lower < 0 or upper < lower):
        return {'decision':'unavailable','reason':'invalid_bounds'}
    decision='execute' if upper < threshold else ('do_not_execute' if lower >= threshold else 'uncertain')
    return {'decision':decision,'lower':lower,'upper':upper,'threshold':threshold,'unit':unit}
