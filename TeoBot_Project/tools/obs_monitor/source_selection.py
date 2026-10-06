"""Conservative arbitration: color supports text, never creates an exact number."""


def fits(current, maximum, evidence):
    available = [e for e in evidence.values() if e.get('available')]
    if not maximum or not 0 <= current <= maximum or not available:
        return False
    percent = 100*current/maximum
    return all(e['lower_percent'] <= percent <= e['upper_percent'] for e in available)


def select_source(top, side, evidence, cached_maximum):
    tv = top.get('value')
    sc = side.get('current')
    top_ok = tv is not None and fits(tv['current'],tv['maximum'],evidence)
    # A sidebar does not observe maximum. Expose only its current value;
    # the last confirmed maximum is used for a consistency check, not as truth.
    side_ok = sc is not None and fits(sc,cached_maximum,evidence)
    result = dict(top,side=side,fill=evidence,value=None,source=None,
                  quality='unconfirmed',verification='unresolved',
                  fill_status='unavailable' if not any(e.get('available') for e in evidence.values()) else 'conflict',
                  source_checks={'top_color_consistent':top_ok,'side_color_consistent':side_ok})
    # Two independently readable counters can support current while both bars
    # are explicitly unavailable. Never ignore a PRESENT conflicting interval,
    # and never learn a new maximum through this fallback.
    no_color = not any(e.get('available') for e in evidence.values())
    if (no_color and tv is not None and sc == tv['current']
            and tv['maximum'] == cached_maximum
            and not side.get('reason')
            and any(e.get('reason') == 'foreign_color_overlay' for e in evidence.values())):
        result.update(value=tv,source='top_and_side_text',quality='exact',
                      verification='current_agrees_without_color',fill_status='unavailable')
        return result
    if top_ok and side_ok and tv['current'] != sc:
        result['verification']='conflict'
        return result
    if top_ok:
        result.update(value=tv,source='top_and_side_text' if side_ok else 'top_text',
                      quality='exact',verification='current_agrees' if side_ok else 'top_color_supported',
                      fill_status='consistent')
    elif side_ok:
        result.update(value={'current':sc,'maximum':None,'percent':None,
                             'last_confirmed_maximum':cached_maximum,
                             'estimated_percent':100*sc/cached_maximum,
                             'maximum_source':'cached_top_text'},
                      source='side_text',quality='current_only',
                      verification='side_color_supported',fill_status='consistent')
    return result
