"""
gh_daily_collect.py — Raccolta dati Google Health del giorno precedente.
Salva in /workspace/.googlehealth/data/YYYY-MM-DD.json
"""
import sys, os
sys.path.insert(0, '/workspace/.googlehealth')

import urllib.request, urllib.error, json
from datetime import datetime, timedelta
from collections import defaultdict
from gh_refresh import get_valid_token

os.makedirs('/workspace/.googlehealth/data', exist_ok=True)

ROME_OFFSET = timedelta(hours=2)

def phys_to_rome(ts):
    if not ts: return None
    return datetime.fromisoformat(ts.replace('Z', '+00:00')) + ROME_OFFSET

def civil_date(civil):
    if not civil: return None
    d = civil.get('date', civil)
    y, mo, day = d.get('year'), d.get('month'), d.get('day')
    return f'{y}-{mo:02d}-{day:02d}' if (y and mo and day) else None

def fmt_h(mins):
    h, m = divmod(int(mins), 60)
    return f'{h}h {m:02d}m'

def get_pages(token, data_type, max_pages=10, page_size=5000):
    BASE = 'https://health.googleapis.com/v4/users/me/dataTypes'
    pts, next_token = [], None
    for _ in range(max_pages):
        url = f'{BASE}/{data_type}/dataPoints?pageSize={page_size}'
        if next_token:
            url += f'&pageToken={next_token}'
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            print(f'  Errore {e.code} su {data_type}')
            break
        pts.extend(data.get('dataPoints', []))
        next_token = data.get('nextPageToken')
        if not next_token:
            break
    return pts

# ── MAIN ──────────────────────────────────────────────────────────────────────
token = get_valid_token()
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
print(f'Raccolta dati per: {yesterday}')

result = {'date': yesterday, 'collected_at': datetime.now().isoformat()}

# ── PASSI ─────────────────────────────────────────────────────────────────────
pts = get_pages(token, 'steps', max_pages=3)
steps_total = sum(
    int(pt['steps']['count'])
    for pt in pts
    if civil_date(pt.get('steps', {}).get('interval', {}).get('civilStartTime')) == yesterday
    and pt.get('steps', {}).get('count')
)
result['steps'] = steps_total
print(f'  Passi: {steps_total}')

# ── CALORIE ATTIVE (campo "kcal") ─────────────────────────────────────────────
pts = get_pages(token, 'active-energy-burned', max_pages=3)
kcal_total = sum(
    float(pt['activeEnergyBurned']['kcal'])
    for pt in pts
    if civil_date(pt.get('activeEnergyBurned', {}).get('interval', {}).get('civilStartTime')) == yesterday
    and pt.get('activeEnergyBurned', {}).get('kcal')
)
result['active_kcal'] = round(kcal_total, 1)
print(f'  Calorie attive: {kcal_total:.0f} kcal')

# ── SONNO (struttura sleep con summary + interval) ────────────────────────────
# Il sonno usa 'interval' (non sampleTime). La notte è identificata da startTime.
pts = get_pages(token, 'sleep', max_pages=3, page_size=10)
sleep_result = None
for pt in pts:
    sl = pt.get('sleep', {})
    summary = sl.get('summary', {})
    ts = sl.get('interval', {}).get('startTime', '')
    if not summary or not ts:
        continue
    dt = phys_to_rome(ts)
    # Assegna la notte: se ora < 12 → è la notte del giorno precedente
    nk = (dt - timedelta(days=1)).strftime('%Y-%m-%d') if dt.hour < 12 else dt.strftime('%Y-%m-%d')
    if nk != yesterday:
        continue

    stages = {s['type'].lower(): int(s['minutes']) for s in summary.get('stagesSummary', [])}
    sleep_result = {
        'total_mins':  int(summary.get('minutesInSleepPeriod', 0)),
        'asleep_mins': int(summary.get('minutesAsleep', 0)),
        'awake_mins':  int(summary.get('minutesAwake', 0)),
        'deep_mins':   stages.get('deep', 0),
        'light_mins':  stages.get('light', 0),
        'rem_mins':    stages.get('rem', 0),
        'total_fmt':   fmt_h(summary.get('minutesInSleepPeriod', 0)),
        'deep_fmt':    fmt_h(stages.get('deep', 0)),
        'rem_fmt':     fmt_h(stages.get('rem', 0)),
    }
    break  # primo match = notte giusta

result['sleep'] = sleep_result
if sleep_result:
    print(f'  Sonno: {sleep_result["total_fmt"]} | deep {sleep_result["deep_fmt"]} | REM {sleep_result["rem_fmt"]} | sveglio {sleep_result["awake_mins"]}m')
else:
    print('  Sonno: nessun dato per ieri')

# ── FC DIURNA (07-22h) ────────────────────────────────────────────────────────
pts = get_pages(token, 'heart-rate', max_pages=10)
hr_vals = [
    int(pt['heartRate']['beatsPerMinute'])
    for pt in pts
    if pt.get('heartRate', {}).get('sampleTime', {}).get('physicalTime')
    and pt['heartRate'].get('beatsPerMinute')
    and (lambda dt: dt.strftime('%Y-%m-%d') == yesterday and 7 <= dt.hour <= 22)(
        phys_to_rome(pt['heartRate']['sampleTime']['physicalTime'])
    )
]
result['heart_rate'] = {
    'avg': round(sum(hr_vals) / len(hr_vals), 1),
    'min': min(hr_vals),
    'max': max(hr_vals),
    'samples': len(hr_vals)
} if hr_vals else None
print(f'  FC: {result["heart_rate"]}')

# ── PESO ──────────────────────────────────────────────────────────────────────
pts = get_pages(token, 'weight', max_pages=1, page_size=20)
if pts:
    last = sorted(pts, key=lambda p: p.get('weight', {}).get('sampleTime', {}).get('physicalTime', ''))[-1]
    kg = last.get('weight', {}).get('kilograms')
    ts = last.get('weight', {}).get('sampleTime', {}).get('physicalTime', '')
    result['weight'] = {'kg': round(float(kg), 1) if kg else None, 'date': phys_to_rome(ts).strftime('%Y-%m-%d') if ts else None}
else:
    result['weight'] = None
print(f'  Peso: {result["weight"]}')

# ── SALVA ─────────────────────────────────────────────────────────────────────
out_path = f'/workspace/.googlehealth/data/{yesterday}.json'
with open(out_path, 'w') as f:
    json.dump(result, f, indent=2)
print(f'\nSalvato in {out_path}')
print(json.dumps(result, indent=2))
