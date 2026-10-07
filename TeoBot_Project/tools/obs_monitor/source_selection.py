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
    # A broad sidebar interval cannot verify a changed top maximum when its
    # own bar is occluded. Keep the cached maximum and independently read side.
    maximum_change_unverified = (tv is not None and cached_maximum is not None
        and tv['maximum'] != cached_maximum
        and not (tv['current'] == tv['maximum'] == sc
                 and evidence.get('top',{}).get('available')
                 and fits(tv['current'],tv['maximum'],evidence)))
    if maximum_change_unverified:
        top_ok = False
    result = dict(top,side=side,fill=evidence,value=None,source=None,
                  quality='unconfirmed',verification='unresolved',
                  fill_status='unavailable' if not any(e.get('available') for e in evidence.values()) else 'conflict',
                  source_checks={'top_color_consistent':top_ok,'side_color_consistent':side_ok})
    # New maximum remains uncommitted, but matching current counters can still
    # be exact. Validate the observed ratio against color, retain cached maximum
    # only as history (it may be smaller than current after a genuine level-up).
    if (maximum_change_unverified and tv['current'] == sc and not side.get('reason')
            and fits(tv['current'],tv['maximum'],evidence)):
        result.update(value={'current':sc,'maximum':None,'percent':None,
                             'last_confirmed_maximum':cached_maximum,
                             'estimated_percent':100*sc/cached_maximum,
                             'maximum_source':'cached_top_text'},
                      source='top_and_side_text',quality='current_only',
                      verification='current_agrees',fill_status='consistent',
                      maximum_update_blocked='changed_maximum_not_verified_at_full_resource')
        return result
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
    if needs_glyph_check(top,side,evidence,cached_maximum) and top.get('glyph_corroborated'):
        result.update(value=tv,source='top_text',quality='exact',
                      verification='top_glyphs_supported_without_color',fill_status='unavailable')
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
    if maximum_change_unverified:
        result['maximum_update_blocked']='changed_maximum_not_verified_at_full_resource'
    return result


def needs_glyph_check(top,side,evidence,cached_maximum):
    value=top.get('value')
    return bool(value is not None and cached_maximum is not None
                and value['maximum']==cached_maximum
                and 0 <= value['current'] <= cached_maximum
                and side.get('current') is None
                and not any(e.get('available') for e in evidence.values())
                and any(e.get('reason')=='foreign_color_overlay' for e in evidence.values()))


def corroborate_top(engine,top,image):
    from glyph_ocr import recover_ratio
    recovery=recover_ratio(engine,image)
    value=top['value']
    return dict(top,glyph_corroboration=recovery,
                glyph_corroborated=recovery['text']==f"{value['current']}/{value['maximum']}")
