# Trend Scraper API Usage Guide

This guide provides `curl` commands and usage instructions for the live Trend Scraper API.

**Base URL:** `http://trend_scraper.172.174.240.250.sslip.io`
**Swagger UI:** `http://trend_scraper.172.174.240.250.sslip.io/docs`

---

## 1. Trends Retrieval

### Get All Recent Trends
Fetches the latest trends across all platforms.
```bash
curl -X GET "http://trend_scraper.172.174.240.250.sslip.io/api/v1/trends/?limit=50"
```

### Get Trends by Platform
Platforms available: `x`, `instagram`, `facebook`, `tiktok`.
```bash
curl -X GET "http://trend_scraper.172.174.240.250.sslip.io/api/v1/trends/x?limit=20"
```

### Search Trends
Perform a full-text search within trend content/captions.
```bash
curl -X GET "http://trend_scraper.172.174.240.250.sslip.io/api/v1/trends/x/search?q=marketing&limit=20"
```

---

## 2. Scraping Control

### Trigger Manual Scrape
Starts a background scrape job immediately.
```bash
curl -X POST "http://trend_scraper.172.174.240.250.sslip.io/api/v1/scrape/" \
     -H "Content-Type: application/json" \
     -d '{
       "platform": "x",
       "limit": 10
     }'
```
*   **platform:** (Optional) `x`, `instagram`, `facebook`, or `tiktok`.
*   **limit:** (Optional) Number of items per keyword.

### Check Scrape Status
Returns whether a job is currently running and when the next scheduled run is.
```bash
curl -X GET "http://trend_scraper.172.174.240.250.sslip.io/api/v1/scrape/status"
```

### View Scrape History
See the status and results of recent scrape jobs.
```bash
curl -X GET "http://trend_scraper.172.174.240.250.sslip.io/api/v1/scrape/jobs?limit=10"
```

---

## 3. Keyword Management

### List All Keywords
```bash
curl -X GET "http://trend_scraper.172.174.240.250.sslip.io/api/v1/keywords"
```

### Add New Keyword
```bash
curl -X POST "http://trend_scraper.172.174.240.250.sslip.io/api/v1/keywords/" \
     -H "Content-Type: application/json" \
     -d '{
       "keyword": "marketing egypt",
       "platform": "tiktok",
       "active": true
     }'
```

### Delete Keyword
```bash
curl -X DELETE "http://trend_scraper.172.174.240.250.sslip.io/api/v1/keywords/{keyword_id}"
```

---

## 🔐 Security

If `API_SECRET_KEY` is configured in the `.env`, you must include the following header in every request:
```bash
-H "Authorization: Bearer YOUR_SECRET_KEY"
```

## 🛠️ n8n Integration
When using the **HTTP Request** node in n8n:
1.  **Method:** Match the methods above (GET/POST/DELETE).
2.  **URL:** Use the paths provided.
3.  **Authentication:** Choose 'Header Authentication' if using a Secret Key.
4.  **Body:** For POST requests, set 'Body Parameters' to 'JSON' and input the parameters.
