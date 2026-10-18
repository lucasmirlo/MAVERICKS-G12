"""Reference priority policy. No network, LLM, or hidden challenge labels."""
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import json
import math

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / 'config/risk_policy.json').read_text())

def number(value, field, minimum=0, maximum=None):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{field}: expected finite number')
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{field}: outside allowed range')
    return float(value)

def band(score):
    if score is None:
        return None
    for row in reversed(POLICY['bands']):
        if score >= row['min']:
            return row['id']
    raise ValueError('score outside policy')

def priority(*, is_risk, severity, criticality, single_source, share_category_pct,
             inventory_days=None, lead_days=None, disruption_days=None,
             inventory_applicability='physical', active=True):
    """Compute priority; missing physical inventory is review, not zero inventory.

    Disruption duration must be selected from explicit source evidence. If it is
    a lower bound, the caller must retain that qualification alongside the result.
    Return historical priority by evaluating active=True before storing resolution.
    """
    if not isinstance(is_risk, bool) or not isinstance(active, bool):
        raise ValueError('is_risk and active must be booleans')
    if inventory_applicability not in {'physical','not_applicable','unknown'}:
        raise ValueError('invalid inventory applicability')
    if criticality is not None and criticality not in POLICY['criticality']:
        raise ValueError('unknown criticality')
    if single_source is not None and single_source not in {'Y','N'}:
        raise ValueError('unknown single_source')
    severity = number(severity,'severity',1,10)
    share = number(share_category_pct,'share_category_pct',0,100)
    inventory = number(inventory_days,'inventory_days')
    lead = number(lead_days,'lead_days')
    duration = number(disruption_days,'disruption_days')
    if lead == 0 or duration == 0:
        raise ValueError('lead and disruption duration must be positive when supplied')
    warnings = []
    factors = {}
    if criticality is not None:
        factors['C'] = POLICY['criticality'][criticality]
    else:
        warnings.append('criticality_missing')
    if single_source is not None:
        factors['U'] = 1.0 if single_source == 'Y' else 0.0
    else:
        warnings.append('single_source_missing')
    if share is not None:
        factors['G'] = share / 100
    else:
        warnings.append('category_share_missing')
    buffers = []
    if inventory_applicability == 'not_applicable':
        if inventory is not None:
            raise ValueError('non-applicable inventory must be null')
    elif inventory_applicability == 'unknown':
        warnings.append('inventory_applicability_unknown')
    elif inventory is None:
        warnings.append('inventory_missing')
    else:
        if lead is not None:
            buffers.append(max(0.0,min(1.0,(lead-inventory)/lead)))
        if duration is not None:
            buffers.append(max(0.0,min(1.0,(duration-inventory)/duration)))
        if buffers:
            factors['B'] = max(buffers)
        else:
            warnings.append('buffer_horizon_missing')
    if is_risk and severity is None:
        warnings.append('severity_missing')
    weights = POLICY['weights']
    denominator = sum(weights[k] for k in factors)
    exposure = sum(weights[k]*v for k,v in factors.items())/denominator if denominator else None
    contributions = {k:weights[k]*v/denominator for k,v in factors.items()} if denominator else {}
    if not is_risk or not active:
        result = 0.0
    elif severity is None or exposure is None:
        result = None
    else:
        raw=100*(severity/10)*(POLICY['severity_floor']+POLICY['exposure_weight']*exposure)
        result=float(Decimal(str(round(raw,10))).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP))
    return {'priority':result,'band':band(result),'exposure':exposure,'factors':factors,
            'contributions':contributions,'warnings':warnings,'needs_review':bool(warnings),
            'policy_version':POLICY['version']}

def decisions(*, p_link, p_risk, p_urgent, impact_status='active', needs_review=False):
    values=[number(x,n,0,1) for n,x in [('p_link',p_link),('p_risk',p_risk),('p_urgent',p_urgent)]]
    if any(x is None for x in values):
        raise ValueError('decision probabilities must be present')
    if impact_status not in {'active','monitoring','resolved','positive','unrelated','unclear'}:
        raise ValueError('invalid impact_status')
    p_link,p_risk,p_urgent=values
    t=POLICY['thresholds']
    linked=p_link>=t['link']
    risk=linked and p_risk>=t['risk']
    urgent=risk and p_urgent>=t['urgent']
    relevant=[p_link]+([p_risk] if linked else [])+([p_urgent] if risk else [])
    ambiguous=any(t['review_low']<=p<=t['review_high'] for p in relevant)
    contradictory=bool(risk and impact_status in {'resolved','positive','unrelated'})
    review=needs_review or ambiguous or contradictory or impact_status=='unclear'
    audible=urgent and impact_status=='active' and not review and min(values)>=t['audible_probability']
    return {'linked':linked,'is_risk':'Y' if risk else 'N','urgent':'Y' if urgent else 'N',
            'needs_review':review,'sound_eligible':audible}
