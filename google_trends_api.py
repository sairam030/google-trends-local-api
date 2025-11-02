"""
Google Trends FastAPI - CSV Export Strategy with Background Updates
Uses Playwright for faster, more reliable scraping
Serves cached data immediately while updating in background
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import aiofiles

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import csv as csv_module

# ============================================================================
# CONFIGURATION
# ============================================================================

CACHE_FILE = "trends_cache.json"
DOWNLOAD_DIR = "downloads"
GEO_DEFAULT = "IN"

CATEGORIES = {
    0: "All Categories",
    1: "Autos and vehicles",
    2: "Beauty and fashion",
    3: "Business and finance",
    20: "Climate",
    4: "Entertainment",
    5: "Food and drink",
    6: "Games",
    7: "Health",
    8: "Hobbies and leisure",
    9: "Jobs and education",
    10: "Law and government",
    11: "Other",
    13: "Pets and animals",
    14: "Politics",
    15: "Science",
    16: "Shopping",
    17: "Sports",
    18: "Technology",
    19: "Travel and transportation",
}

# ============================================================================
# DATA MODELS
# ============================================================================

class TrendItem(BaseModel):
    rank: int
    title: str
    traffic: Optional[str] = None
    article_title: Optional[str] = None
    article_source: Optional[str] = None
    timestamp: str

class CategoryTrends(BaseModel):
    category_id: int
    category_name: str
    trend_count: int
    trends: List[TrendItem]
    last_updated: str

class TrendsResponse(BaseModel):
    status: str
    geography: str
    categories: Dict[str, CategoryTrends]
    metadata: Dict
    cache_info: Dict

# ============================================================================
# CACHE MANAGER
# ============================================================================

class TrendsCache:
    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache_file = cache_file
        self.data = None
        self.last_update = None
        self.update_in_progress = False
        
    async def load(self) -> Optional[Dict]:
        """Load cache from disk"""
        try:
            if not os.path.exists(self.cache_file):
                return None
            
            async with aiofiles.open(self.cache_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self.data = json.loads(content)
                self.last_update = datetime.fromisoformat(
                    self.data.get('metadata', {}).get('last_updated', datetime.now().isoformat())
                )
                return self.data
        except Exception as e:
            print(f"❌ Error loading cache: {e}")
            return None
    
    async def save(self, data: Dict):
        """Save cache to disk"""
        try:
            async with aiofiles.open(self.cache_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
            self.data = data
            self.last_update = datetime.now()
            print(f"✅ Cache saved: {self.cache_file}")
        except Exception as e:
            print(f"❌ Error saving cache: {e}")
    
    def is_stale(self, max_age_minutes: int = 2) -> bool:
        """Check if cache is older than max_age_minutes"""
        if not self.last_update:
            return True
        age = datetime.now() - self.last_update
        return age > timedelta(minutes=max_age_minutes)
    
    def get_cache_info(self) -> Dict:
        """Get cache status information"""
        return {
            "cached": self.data is not None,
            "last_updated": self.last_update.isoformat() if self.last_update else None,
            "age_minutes": round((datetime.now() - self.last_update).total_seconds() / 60, 2) if self.last_update else None,
            "update_in_progress": self.update_in_progress,
            "stale": self.is_stale()
        }

# ============================================================================
# SELENIUM SCRAPER - CSV DOWNLOAD STRATEGY
# ============================================================================

class SeleniumTrendsScraper:
    def __init__(self, geo: str = GEO_DEFAULT):
        self.geo = geo
        self.download_dir = Path(DOWNLOAD_DIR)
        self.download_dir.mkdir(exist_ok=True)
        self.driver = None
        
    def _setup_driver(self):
        """Initialize Chrome driver with download preferences"""
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Download preferences
        prefs = {
            "download.default_directory": str(self.download_dir.absolute()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Enable downloads via CDP
        self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": str(self.download_dir.absolute())
        })
        
        return self.driver
        
    def scrape_category_csv(self, category_id: int) -> List[Dict]:
        """
        Scrape a category using CSV download (Export -> Download CSV)
        Falls back to HTML if CSV fails
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time
        import glob
        
        category_name = CATEGORIES.get(category_id, f"Category {category_id}")
        driver = None
        
        try:
            driver = self._setup_driver()
            wait = WebDriverWait(driver, 20)
            trends_data = []
            csv_downloaded = False
            
            # Build URL
            if category_id != 0:
                url = f"https://trends.google.com/trending?geo={self.geo}&category={category_id}"
            else:
                url = f"https://trends.google.com/trending?geo={self.geo}"
            
            print(f"  📡 Loading: {category_name}")
            
            # Navigate to page
            driver.get(url)
            time.sleep(3)  # Wait for page load
            
            # Try CSV download
            try:
                # Step 1: Click "Export" button
                export_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Export')]")))
                print(f"    ✅ Found Export button")
                driver.execute_script("arguments[0].click();", export_btn)
                time.sleep(3)  # Wait longer for dropdown menu
                
                # Step 2: Click "Download CSV" - try multiple selectors
                csv_clicked = False
                selectors = [
                    "//span[contains(text(), 'Download CSV')]",
                    "//div[contains(text(), 'Download CSV')]",
                    "//*[contains(text(), 'Download CSV')]",
                    "//button[contains(., 'CSV')]",
                    "//div[@role='menuitem' and contains(., 'CSV')]"
                ]
                
                for selector in selectors:
                    try:
                        csv_element = driver.find_element(By.XPATH, selector)
                        parent = csv_element.find_element(By.XPATH, "./ancestor::button | ./ancestor::div[@role='menuitem'] | ./parent::*")
                        
                        print(f"    ✅ Found Download CSV option (selector: {selector[:30]}...)")
                        
                        # Get list of files before download
                        before_files = set(glob.glob(str(self.download_dir / "*.csv")))
                        
                        # Click to download
                        driver.execute_script("arguments[0].click();", parent)
                        
                        # Wait for download to complete
                        timeout = 20
                        downloaded_file = None
                        for _ in range(timeout):
                            time.sleep(1)
                            after_files = set(glob.glob(str(self.download_dir / "*.csv")))
                            new_files = after_files - before_files
                            if new_files:
                                downloaded_file = list(new_files)[0]
                                break
                        
                        if downloaded_file:
                            csv_path = Path(downloaded_file)
                            print(f"    💾 CSV downloaded: {csv_path.name}")
                            
                            # Parse CSV
                            trends_data = self._parse_csv_sync(csv_path, category_id)
                            csv_downloaded = True
                            csv_clicked = True
                            break
                        else:
                            print(f"    ⚠️  CSV download timeout after click")
                            
                    except Exception as e:
                        continue
                
                if not csv_clicked:
                    print(f"    ⚠️  Download CSV option not found in menu")
                    
            except Exception as e:
                print(f"    ⚠️  CSV download failed: {str(e)[:80]}")
            
            # Fallback: HTML scraping if CSV failed
            if not csv_downloaded:
                print(f"    🔄 Fallback: HTML scraping...")
                trends_data = self._scrape_html_selenium(driver, category_id)
            
            if trends_data:
                print(f"    ✅ Got {len(trends_data)} trends")
            else:
                print(f"    ⚠️  No trends found")
            
            return trends_data
            
        except Exception as e:
            print(f"    ❌ Error: {str(e)[:100]}")
            return []
        finally:
            if driver:
                driver.quit()
    
    def _parse_csv_sync(self, csv_path: Path, category_id: int) -> List[Dict]:
        """Parse downloaded CSV file (synchronous)"""
        import csv
        
        trends = []
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for idx, row in enumerate(reader, 1):
                    # Google Trends CSV columns
                    trend = {
                        "rank": idx,
                        "title": row.get('Trends', row.get('Query', row.get('Title', row.get('Search term', '')))).strip().lower(),
                        "traffic": row.get('Search volume', row.get('Traffic', row.get('Approximate searches', ''))),
                        "started": row.get('Started', ''),
                        "ended": row.get('Ended', ''),
                        "trend_breakdown": row.get('Trend breakdown', ''),
                        "explore_link": row.get('Explore link', ''),
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # Only add if title is not empty
                    if trend["title"]:
                        trends.append(trend)
                
            print(f"    ✅ Parsed {len(trends)} trends from CSV")
            
        except Exception as e:
            print(f"    ❌ Error parsing CSV: {e}")
        
        return trends
    
    def _scrape_html_selenium(self, driver, category_id: int) -> List[Dict]:
        """Fallback: scrape HTML table if CSV unavailable (Selenium)"""
        from selenium.webdriver.common.by import By
        
        trends = []
        
        try:
            # Extract table rows
            rows = driver.find_elements(By.CSS_SELECTOR, 'table tbody tr, .feed-item')
            
            for idx, row in enumerate(rows, 1):
                try:
                    text = row.text
                    parts = [p.strip() for p in text.split('\n') if p.strip()]
                    
                    if not parts:
                        continue
                    
                    title = parts[0]
                    traffic = next((p for p in parts if any(x in p for x in ['K+', 'M+', '+'])), None)
                    
                    trend = {
                        "rank": idx,
                        "title": title.lower(),
                        "traffic": traffic,
                        "article_title": parts[1] if len(parts) > 1 else None,
                        "article_source": None,
                        "timestamp": datetime.now().isoformat()
                    }
                    trends.append(trend)
                    
                except Exception as e:
                    continue
            
            print(f"    ✅ Scraped {len(trends)} trends from HTML")
            
        except Exception as e:
            print(f"    ❌ Error scraping HTML: {e}")
        
        return trends
    
    def scrape_all_categories(self, categories: Optional[List[int]] = None) -> Dict:
        """Scrape all requested categories"""
        if categories is None:
            # Default: all categories except "All Categories" (0)
            categories = [cid for cid in CATEGORIES.keys() if cid != 0]
        
        print(f"\n🚀 Starting scrape for {len(categories)} categories...")
        start_time = datetime.now()
        
        results = {
            "geography": self.geo,
            "categories": {},
            "metadata": {
                "scrape_started": start_time.isoformat(),
                "last_updated": None,
                "total_trends": 0,
                "categories_count": 0,
                "source": "playwright_csv_export"
            }
        }
        
        # Scrape each category
        for idx, cat_id in enumerate(categories, 1):
            cat_name = CATEGORIES.get(cat_id, f"Category {cat_id}")
            print(f"\n[{idx}/{len(categories)}] {cat_name}...")
            
            trends = self.scrape_category_csv(cat_id)
            
            results["categories"][cat_name] = {
                "category_id": cat_id,
                "category_name": cat_name,
                "trend_count": len(trends),
                "trends": trends,
                "last_updated": datetime.now().isoformat()
            }
            
            results["metadata"]["total_trends"] += len(trends)
            results["metadata"]["categories_count"] += 1
        
        end_time = datetime.now()
        results["metadata"]["last_updated"] = end_time.isoformat()
        results["metadata"]["scrape_duration_seconds"] = (end_time - start_time).total_seconds()
        
        print(f"\n✅ Scraping complete! Total trends: {results['metadata']['total_trends']}")
        
        return results

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Google Trends API",
    description="Real-time Google Trends data with caching and background updates",
    version="2.0.0"
)

# Global cache instance
cache = TrendsCache()

# Scheduler for automatic updates
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    """Initialize cache and start background scheduler"""
    print("🚀 Starting Google Trends API...")
    
    # Load cache from disk
    await cache.load()
    
    if cache.data:
        print(f"✅ Cache loaded from disk")
    else:
        print("⚠️  No cache found, starting initial scrape...")
        # Trigger initial scrape on startup
        asyncio.create_task(update_cache_background())
    
    # Schedule automatic updates every 2 minutes
    scheduler.add_job(
        scheduled_update,
        'interval',
        minutes=2,
        id='auto_update',
        replace_existing=True
    )
    scheduler.start()
    print("✅ Scheduled auto-updates every 2 minutes")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    scheduler.shutdown()
    print("👋 API shutdown")

# ============================================================================
# BACKGROUND UPDATE FUNCTION
# ============================================================================

async def update_cache_background():
    """Background task to update cache"""
    if cache.update_in_progress:
        print("⚠️  Update already in progress, skipping...")
        return
    
    try:
        cache.update_in_progress = True
        print("\n" + "="*70)
        print("🔄 BACKGROUND UPDATE STARTED")
        print("="*70)
        
        # Scrape fresh data (run in thread pool since Selenium is sync)
        loop = asyncio.get_event_loop()
        scraper = SeleniumTrendsScraper(geo=GEO_DEFAULT)
        fresh_data = await loop.run_in_executor(None, scraper.scrape_all_categories)
        
        # Save to cache
        await cache.save(fresh_data)
        
        print("="*70)
        print("✅ BACKGROUND UPDATE COMPLETED")
        print(f"📊 Total trends: {fresh_data['metadata']['total_trends']}")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"❌ Background update failed: {e}")
    finally:
        cache.update_in_progress = False

async def scheduled_update():
    """Scheduled update job"""
    print("⏰ Scheduled update triggered...")
    await update_cache_background()

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", response_model=Dict)
async def root():
    """API info"""
    return {
        "service": "Google Trends API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "trends": "/api/trends",
            "force_update": "/api/update",
            "health": "/health"
        }
    }

@app.get("/api/trends")
async def get_trends(
    background_tasks: BackgroundTasks,
    geo: str = Query(default=GEO_DEFAULT, description="Geography code (IN, US, GB, etc.)"),
    category: Optional[str] = Query(default=None, description="Specific category name"),
    flat: bool = Query(default=True, description="Return flattened list of all trends"),
    force_refresh: bool = Query(default=False, description="Force fresh scrape")
):
    """
    Get Google Trends data
    
    - Returns cached data immediately (if available)
    - flat=true returns single list with category in each trend
    - flat=false returns grouped by category
    - Use force_refresh=true to scrape fresh data (slower)
    """
    
    # Wait for cache if initial scrape is in progress
    max_wait = 120  # 2 minutes max wait
    waited = 0
    while not cache.data and cache.update_in_progress and waited < max_wait:
        await asyncio.sleep(1)
        waited += 1
    
    # Check if we have cached data
    if cache.data and not force_refresh:
        # Return cache immediately
        response_data = cache.data.copy()
        
        # Filter by category if requested
        if category is not None:
            if category in response_data.get("categories", {}):
                response_data["categories"] = {
                    category: response_data["categories"][category]
                }
            else:
                raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
        
        # Flatten response if requested
        if flat:
            all_trends = []
            geography = response_data.get("geography", geo)
            for cat_name, cat_data in response_data.get("categories", {}).items():
                for trend in cat_data.get("trends", []):
                    # Add category and geography info to each trend
                    trend_with_category = trend.copy()
                    trend_with_category["category"] = cat_name
                    trend_with_category["category_id"] = cat_data.get("category_id")
                    trend_with_category["geography"] = geography
                    all_trends.append(trend_with_category)
            
            response_data["trends"] = all_trends
            response_data["total_count"] = len(all_trends)
            # Remove nested categories structure
            del response_data["categories"]
        
        response_data["cache_info"] = cache.get_cache_info()
        
        return JSONResponse(content=response_data)
    
    # No cache or force refresh - scrape now (slower)
    print("🔄 No cache available or force refresh requested, scraping now...")
    
    scraper = SeleniumTrendsScraper(geo=geo)
    loop = asyncio.get_event_loop()
    fresh_data = await loop.run_in_executor(None, scraper.scrape_all_categories)
    
    # Save to cache
    await cache.save(fresh_data)
    
    # Flatten if requested
    if flat:
        all_trends = []
        geography = fresh_data.get("geography", geo)
        for cat_name, cat_data in fresh_data.get("categories", {}).items():
            for trend in cat_data.get("trends", []):
                trend_with_category = trend.copy()
                trend_with_category["category"] = cat_name
                trend_with_category["category_id"] = cat_data.get("category_id")
                trend_with_category["geography"] = geography
                all_trends.append(trend_with_category)
        
        fresh_data["trends"] = all_trends
        fresh_data["total_count"] = len(all_trends)
        del fresh_data["categories"]
    
    fresh_data["cache_info"] = cache.get_cache_info()
    
    return JSONResponse(content=fresh_data)

@app.post("/api/update")
async def force_update(background_tasks: BackgroundTasks):
    """
    Force a background cache update
    Returns immediately, update runs in background
    """
    if cache.update_in_progress:
        return {
            "status": "update_already_running",
            "message": "An update is already in progress"
        }
    
    background_tasks.add_task(update_cache_background)
    
    return {
        "status": "update_triggered",
        "message": "Background update has been triggered",
        "cache_info": cache.get_cache_info()
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "cache": cache.get_cache_info(),
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*70)
    print("🚀 Google Trends FastAPI Server")
    print("="*70)
    print("📝 Strategy: CSV Export + Background Caching")
    print("🎭 Scraper: Playwright (faster than Selenium)")
    print("⏰ Auto-updates: Every 2 minutes")
    print("📊 Response: Flattened JSON (each trend has category)")
    print("="*70 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8888,
        log_level="info"
    )
