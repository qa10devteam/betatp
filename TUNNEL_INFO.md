# Cloudflare Tunnel — betatp.io API

## PUBLIC URL
**https://certified-shareware-joy-session.trycloudflare.com**

## Status (2026-06-26)
- Metoda: Cloudflare Quick Tunnel (trycloudflare.com)
- Wersja cloudflared: 2026.6.1
- Protokół: QUIC → HTTP
- PID procesu: 369891 (sprawdź: `ps aux | grep cloudflared`)

## Wyniki testów
```
GET /health       → {"status":"ok","version":"0.1.0"}
GET /predictions/model/info → model version: v14 | AUC: 0.9031
```

## Jak uruchomić tunel ponownie
```bash
# Sprawdź czy API działa
curl -s http://localhost:8000/health

# Jeśli nie — uruchom API:
cd /home/ubuntu/betatp
export PYTHONPATH=.
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1 > /tmp/betatp-api.log 2>&1 &

# Uruchom tunel cloudflared:
cloudflared tunnel --url http://localhost:8000 --no-autoupdate > /tmp/cf-tunnel.log 2>&1 &
sleep 10
grep trycloudflare.com /tmp/cf-tunnel.log
```

## Uwagi — wygasanie
- **Quick tunnel NIE ma gwarantowanego czasu działania** — URL zmienia się po każdym restarcie
- Przy restarcie otrzymasz NOWY URL (np. random-words.trycloudflare.com)
- Tunel żyje dopóki żyje proces `cloudflared` — nie wygasa z upływem czasu
- Aby URL był stały → załóż konto Cloudflare i utwórz named tunnel:
  https://developers.cloudflare.com/cloudflare-one/connections/connect-apps

## Podtrzymanie tunelu
```bash
# Sprawdź status
ps aux | grep cloudflared
tail -f /tmp/cf-tunnel.log

# Pełne logi
cat /tmp/cf-tunnel.log | grep -E "(trycloudflare|INF|WRN|ERR)"
```
