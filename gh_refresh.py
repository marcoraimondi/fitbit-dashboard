"""
gh_refresh.py — Aggiorna l'access token Google Health via Cloudflare Worker.
Usato da tutti gli script come import oppure direttamente da riga di comando.
"""
import urllib.request, urllib.error, json, os

TOKENS_PATH = '/workspace/.googlehealth/tokens.json'
WORKER_URL  = 'https://odd-cloud-7fd2.marco-raimondi.workers.dev/refresh'

def load_tokens():
    with open(TOKENS_PATH) as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKENS_PATH, 'w') as f:
        json.dump(tokens, f, indent=2)

def refresh_access_token():
    tokens = load_tokens()
    payload = json.dumps({
        'refresh_token': tokens['refresh_token'],
        'client_id':     tokens['client_id']
    }).encode()
    req = urllib.request.Request(
        WORKER_URL,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Refresh fallito HTTP {e.code}: {e.read().decode()}')

    new_token = resp.get('access_token')
    if not new_token:
        raise RuntimeError(f'Risposta refresh senza access_token: {resp}')

    tokens['access_token'] = new_token
    save_tokens(tokens)
    return new_token

def get_valid_token():
    """Ritorna access_token, rinnovandolo se necessario."""
    tokens = load_tokens()
    token = tokens['access_token']

    # Prova una chiamata leggera per verificare validità
    test_url = 'https://health.googleapis.com/v4/users/me/dataTypes/steps/dataPoints?pageSize=1'
    req = urllib.request.Request(test_url, headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()  # ok, token valido
        return token
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print('[gh_refresh] Token scaduto, rinnovo...')
            return refresh_access_token()
        raise  # altri errori: rilancia

if __name__ == '__main__':
    tok = refresh_access_token()
    print('Token aggiornato:', tok[:30] + '...')
