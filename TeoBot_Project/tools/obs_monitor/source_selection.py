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
    # A failing secondary fill is not a veto over a verified primary pair.
    # Two matching counters + top fill identify an inconsistent sidebar fill;
    # an explicitly covered sidebar counter also makes that local fill suspect.
    # Preserve the measurement for diagnostics, without relabeling a disagreement
    # as proven physical occlusion. Different readable counters remain ambiguous.
    own_top = tv is not None and fits(tv['current'],tv['maximum'],{'top':evidence.get('top',{})})
    sidebar_fill = evidence.get('sidebar',{})
    sidebar_conflict = (tv is not None and sidebar_fill.get('available')
        and not fits(tv['current'],tv['maximum'],{'sidebar':sidebar_fill}))
    ignored_sidebar = None
    if (own_top and sidebar_conflict and tv['maximum'] == cached_maximum
            and ((sc == tv['current'] and not side.get('reason'))
                 or (sc is None and side.get('reason') == 'foreign_color_overlay'))):
        ignored_sidebar = dict(sidebar_fill)
        evidence = dict(evidence,sidebar=dict(sidebar_fill,available=False,
            reason='secondary_fill_untrusted',measured_interval=ignored_sidebar))

    ignored_top = None
    if (tv is not None and sc == tv['current'] and not side.get('reason')
            and tv['maximum'] == cached_maximum
            and fits(sc,cached_maximum,{'sidebar':evidence.get('sidebar',{})})
            and evidence.get('top',{}).get('available') and not own_top):
        ignored_top = dict(evidence['top'])
        evidence = dict(evidence,top=dict(ignored_top,available=False,
            reason='secondary_fill_untrusted',measured_interval=ignored_top))
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
    if ignored_top is not None:
        result['ignored_top_fill'] = ignored_top
        result['source_checks']['top_fill_ignored'] = True
    if ignored_sidebar is not None:
        result['ignored_secondary_fill'] = ignored_sidebar
        result['source_checks']['sidebar_fill_ignored'] = True
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
    # Bound only a residual ambiguity: each candidate must fit EVERY remaining
    # trustworthy fill. A discriminated OCR error must not enter the range.
    if (top_ok and side_ok and sc != tv['current']
            and not side.get('reason') and tv['maximum'] == cached_maximum
            and fits(tv['current'],tv['maximum'],{'top':evidence.get('top',{})})
            and fits(sc,cached_maximum,{'sidebar':evidence.get('sidebar',{})})):
        lower,upper=sorted((tv['current'],sc))
        return dict(top,side=side,fill=evidence,value=None,source='top_and_side_text',
            quality='bounded_conflict',verification='bounded_conflict',fill_status='consistent',
            candidate_range={'lower':lower,'upper':upper,'maximum':cached_maximum,
                'maximum_is_cached':True,'lower_percent':100*lower/cached_maximum,
                'upper_percent':100*upper/cached_maximum},
            range_candidates={'top':tv['current'],'sidebar':sc})
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
