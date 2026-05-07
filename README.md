# Trend Scraper

Scrapes trending posts from **X (Twitter)**, **Instagram**, and **Facebook** by keyword/hashtag. Stores results in Supabase. Runs automatically at random intervals (4–12 hours) to avoid bot detection patterns.

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
```

Fill in your Supabase service role key and platform cookies (see below).

### 2. Extract Cookies from Your Browser

You need to be **already logged in** to each platform in your browser.

#### How to Extract (Chrome / Edge)

1. Open the platform in your browser (x.com, instagram.com, facebook.com)
2. Press `F12` → open DevTools
3. Go to **Application** tab → **Cookies** (left sidebar)
4. Find and copy the values listed below

| Platform | Cookie Name | `.env` Variable |
|---|---|---|
| x.com | `auth_token` | `X_AUTH_TOKEN` |
| x.com | `ct0` | `X_CT0` |
| instagram.com | `sessionid` | `INSTAGRAM_SESSION_ID` |
| instagram.com | `csrftoken` | `INSTAGRAM_CSRF_TOKEN` |
| facebook.com | `c_user` | `FACEBOOK_C_USER` |
| facebook.com | `xs` | `FACEBOOK_XS` |
| facebook.com | `datr` | `FACEBOOK_DATR` |

> ⚠️ Use dedicated/burner accounts — not your personal ones.

#### Quick Extract via Browser Console

Open DevTools Console (`F12` → Console) and run:

**For X (x.com):**
```javascript
console.log('auth_token:', document.cookie.match(/auth_token=([^;]+)/)?.[1]);
console.log('ct0:', document.cookie.match(/ct0=([^;]+)/)?.[1]);
```

**For Instagram:**
```javascript
console.log('sessionid:', document.cookie.match(/sessionid=([^;]+)/)?.[1]);
console.log('csrftoken:', document.cookie.match(/csrftoken=([^;]+)/)?.[1]);
```

**For Facebook:**
```javascript
console.log('c_user:', document.cookie.match(/c_user=([^;]+)/)?.[1]);
console.log('datr:', document.cookie.match(/datr=([^;]+)/)?.[1]);
```

> Note: Some cookies are `HttpOnly` (not accessible via JS). For those, use the DevTools **Application** tab directly.

### 3. Add Keywords

After deployment, add keywords via the API:

```bash
# Add a keyword for X
curl -X POST http://localhost:8000/api/v1/keywords \
  -H "Content-Type: application/json" \
  -d '{"keyword": "AI", "platform": "x"}'

# Add the same keyword for Instagram
curl -X POST http://localhost:8000/api/v1/keywords \
  -H "Content-Type: application/json" \
  -d '{"keyword": "AI", "platform": "instagram"}'
```

### 4. Run Locally (Docker)

```bash
docker compose up --build
```

API available at `http://localhost:8000`  
Docs at `http://localhost:8000/docs`

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/keywords` | List all tracked keywords |
| `POST` | `/api/v1/keywords` | Add keyword `{"keyword": "...", "platform": "x\|instagram\|facebook"}` |
| `PATCH` | `/api/v1/keywords/{id}` | Enable/disable a keyword `{"active": false}` |
| `DELETE` | `/api/v1/keywords/{id}` | Delete a keyword |
| `POST` | `/api/v1/scrape` | Trigger manual scrape |
| `GET` | `/api/v1/scrape/status` | Check if scrape is running + next scheduled run |
| `GET` | `/api/v1/scrape/jobs` | Recent scrape job history |
| `GET` | `/api/v1/trends` | All trends (filter: `?platform=x&keyword=AI&since=2025-01-01`) |
| `GET` | `/api/v1/trends/{platform}` | Trends for one platform |
| `GET` | `/api/v1/trends/{platform}/search?q=topic` | Full-text search |

---

## Bot Detection Webhook

When a CAPTCHA or bot wall is detected, a `POST` request is sent to `BOT_DETECTION_WEBHOOK_URL` with this payload:

```json
{
  "event": "bot_detection",
  "platform": "instagram",
  "keyword": "AI",
  "url": "https://www.instagram.com/explore/tags/AI/",
  "timestamp": "2025-05-07T10:00:00Z",
  "message": "Bot detection triggered on instagram while scraping 'AI'. Human review required.",
  "screenshot_base64": "..."
}
```

If `BOT_DETECTION_WEBHOOK_SECRET` is set, the request includes `X-Webhook-Signature: sha256=<hmac>` for verification.

---

## Coolify Deployment

1. Push this repo to your Git provider
2. In Coolify: **New Service** → **Docker** → point to your repo
3. Set the **Dockerfile** path to `./Dockerfile`
4. Add all env vars from `.env.example` in Coolify's environment panel
5. Set **Health Check URL** to `/api/v1/health`
6. Deploy

For proxy: set `HTTP_PROXY` and `HTTPS_PROXY` to your Hostinger proxy URL.

---

## Scheduling

Scraping runs automatically at a **random interval** between `SCRAPE_INTERVAL_MIN_HOURS` (default: 4h) and `SCRAPE_INTERVAL_MAX_HOURS` (default: 12h). The randomness prevents detectable timing patterns.

Check the next scheduled run:
```bash
curl http://localhost:8000/api/v1/scrape/status
```
