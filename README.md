# Google Trends API with Selenium

A FastAPI-based service that scrapes Google Trends data using Selenium, with automatic background updates and caching.

## 📋 Features

- **Selenium CSV Download**: Reliably downloads trending data via CSV export
- **19 Categories**: Scrapes all Google Trends categories
- **Auto-Updates**: Background scraping every 2 minutes
- **Persistent Cache**: Saves data to `trends_cache.json`
- **Flattened Response**: Each trend includes category and geography
- **RESTful API**: FastAPI endpoints for easy integration

## 📦 Requirements

- Python 3.8+
- Chrome/Chromium browser
- Virtual environment (recommended)

## 🚀 Quick Start

### 1. Setup Virtual Environment

```bash
cd /home/ram/google-trends
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Server

```bash
python google_trends_api.py
```

The server will start on `http://localhost:8888`

## 🔧 Server Management

### Start Server (Background)

```bash
cd /home/ram/google-trends
source venv/bin/activate
nohup python google_trends_api.py > server.log 2>&1 &
```

### Stop Server

```bash
pkill -f "python.*google_trends_api.py"
```

### Restart Server

```bash
pkill -f "python.*google_trends_api.py" && sleep 2 && \
cd /home/ram/google-trends && source venv/bin/activate && \
nohup python google_trends_api.py > server.log 2>&1 &
```

### Check Server Status

```bash
curl http://localhost:8888/health
```

### View Logs

```bash
tail -f server.log
```

## 📡 API Endpoints

### Get All Trends (Flattened)

```bash
curl "http://localhost:8888/api/trends?flat=true"
```

**Response Format:**
```json
{
  "geography": "IN",
  "metadata": {
    "total_trends": 144,
    "categories_count": 19,
    "last_updated": "2025-11-02T23:50:00.000000"
  },
  "trends": [
    {
      "rank": 2,
      "title": "jiohotstar",
      "traffic": "100K+",
      "category": "Technology",
      "category_id": 18,
      "geography": "IN",
      "started": "November 2, 2025 at 1:50:00 PM UTC+5:30",
      "ended": "November 2, 2025 at 3:20:00 PM UTC+5:30",
      "trend_breakdown": "jiohotstar,jio hotstar,hotstar jio",
      "explore_link": "https://trends.google.com/trends/explore?q=jiohotstar&geo=IN",
      "timestamp": "2025-11-02T23:50:21.157939"
    }
  ]
}
```

### Get Trends Grouped by Category

```bash
curl "http://localhost:8888/api/trends?flat=false"
```

### Force Fresh Scrape

```bash
curl "http://localhost:8888/api/trends?force_refresh=true&flat=true"
```

**Note:** This takes ~3-4 minutes to scrape all 19 categories

### Trigger Background Update

```bash
curl -X POST "http://localhost:8888/api/update"
```

### Health Check

```bash
curl "http://localhost:8888/health"
```

### API Info

```bash
curl "http://localhost:8888/"
```

## 🗂️ Project Structure

```
google-trends/
├── google_trends_api.py      # Main FastAPI application
├── requirements.txt           # Python dependencies
├── trends_cache.json         # Cached trends data
├── venv/                     # Virtual environment
└── README.md                 # This file
```

## ⚙️ Configuration

Edit these constants in `google_trends_api.py`:

```python
GEO_DEFAULT = "IN"           # Default geography (IN, US, GB, etc.)
CACHE_FILE = "trends_cache.json"
UPDATE_INTERVAL_MINUTES = 2  # Auto-update frequency
```

## 📊 Available Categories

1. Autos and vehicles
2. Beauty and fashion
3. Business and finance
4. Climate
5. Entertainment
6. Food and drink
7. Games
8. Health
9. Hobbies and leisure
10. Jobs and education
11. Law and government
12. Other
13. Pets and animals
14. Politics
15. Science
16. Shopping
17. Sports
18. Technology
19. Travel and transportation



## 🛠️ Troubleshooting

### Server not starting

```bash
# Check if port 8888 is already in use
lsof -i :8888

# Kill process using the port
kill -9 <PID>
```

### Chrome/Chromedriver issues

```bash
# Install Chrome
sudo apt update
sudo apt install google-chrome-stable

# Webdriver-manager will auto-download chromedriver
```

### View detailed logs

```bash
# Start server in foreground (not background)
cd /home/ram/google-trends
source venv/bin/activate
python google_trends_api.py
```

## 📝 Notes

- First scrape takes ~3-4 minutes for all 19 categories
- Subsequent requests use cached data (instant response)
- Cache auto-updates every 2 minutes in background
- Each trend includes: rank, title, traffic, category, geography, timestamps, explore links
- CSV download is reliable but slower than HTML scraping

## 📄 License

MIT License

## 🤝 Support

For issues or questions, check the server logs:
```bash
tail -f server.log
```
# google-trends-local-api
