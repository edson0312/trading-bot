import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz
import json
import os

class NewsHandler:
    def __init__(self):
        self.cache_file = "news_cache.json"
        self.cache_duration = timedelta(hours=1)
        self.news_cache = self._load_cache()
        
    def _load_cache(self):
        """Load news data from cache file"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    # Convert string timestamps back to datetime objects
                    for news in cache_data:
                        news['timestamp'] = datetime.fromisoformat(news['timestamp'])
                    return cache_data
            except:
                return []
        return []
    
    def _save_cache(self):
        """Save news data to cache file"""
        cache_data = self.news_cache.copy()
        # Convert datetime objects to strings for JSON serialization
        for news in cache_data:
            news['timestamp'] = news['timestamp'].isoformat()
        
        with open(self.cache_file, 'w') as f:
            json.dump(cache_data, f)
    
    def _is_cache_valid(self):
        """Check if the cache is still valid"""
        if not self.news_cache:
            return False
        
        # Check if any news in cache is older than cache_duration
        now = datetime.now(pytz.UTC)
        return all(now - news['timestamp'] < self.cache_duration for news in self.news_cache)
    
    def fetch_high_impact_news(self):
        """Fetch high impact news from Forex Factory"""
        if self._is_cache_valid():
            return self.news_cache
        
        try:
            # Forex Factory API endpoint (you'll need to replace with actual API endpoint)
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            response = requests.get(url)
            response.raise_for_status()
            
            news_data = response.json()
            high_impact_news = []
            
            # Convert to UTC timezone
            utc = pytz.UTC
            
            for news in news_data:
                if news.get('impact') == 'High':
                    # Parse the timestamp
                    timestamp = datetime.strptime(f"{news['date']} {news['time']}", "%Y-%m-%d %H:%M")
                    timestamp = utc.localize(timestamp)
                    
                    # Get affected currencies
                    currency = news.get('currency', '')
                    
                    high_impact_news.append({
                        'timestamp': timestamp,
                        'currency': currency,
                        'event': news.get('event', ''),
                        'impact': news.get('impact', ''),
                        'actual': news.get('actual', ''),
                        'forecast': news.get('forecast', ''),
                        'previous': news.get('previous', '')
                    })
            
            # Update cache
            self.news_cache = high_impact_news
            self._save_cache()
            
            return high_impact_news
            
        except Exception as e:
            print(f"Error fetching news: {e}")
            return []
    
    def get_upcoming_news(self, currency=None, minutes_ahead=60):
        """Get upcoming high impact news for a specific currency"""
        now = datetime.now(pytz.UTC)
        news = self.fetch_high_impact_news()
        
        upcoming_news = []
        for item in news:
            # Check if news is in the future and within the specified time window
            if (item['timestamp'] > now and 
                (item['timestamp'] - now).total_seconds() <= minutes_ahead * 60):
                
                # If currency is specified, only include news for that currency
                if currency is None or item['currency'] == currency:
                    upcoming_news.append(item)
        
        return sorted(upcoming_news, key=lambda x: x['timestamp'])
    
    def is_news_time(self, currency, minutes_before=5):
        """Check if we're within the specified minutes before a high impact news event"""
        upcoming_news = self.get_upcoming_news(currency, minutes_before)
        return len(upcoming_news) > 0
    
    def get_news_stop_levels(self, symbol, current_price, stop_points):
        """Calculate buy stop and sell stop levels for news trading"""
        # Convert points to price
        point_value = 0.0001 if 'JPY' not in symbol else 0.01
        price_adjustment = stop_points * point_value
        
        return {
            'buy_stop': current_price + price_adjustment,
            'sell_stop': current_price - price_adjustment
        }

# Example usage
if __name__ == "__main__":
    handler = NewsHandler()
    
    # Test fetching news
    news = handler.fetch_high_impact_news()
    print("High Impact News:")
    for item in news:
        print(f"{item['timestamp']} - {item['currency']}: {item['event']}")
    
    # Test upcoming news for EUR
    upcoming = handler.get_upcoming_news('EUR', 60)
    print("\nUpcoming EUR News (next 60 minutes):")
    for item in upcoming:
        print(f"{item['timestamp']}: {item['event']}")
    
    # Test stop levels calculation
    levels = handler.get_news_stop_levels('EURUSD', 1.07939, 200)
    print("\nStop Levels for EURUSD:")
    print(f"Buy Stop: {levels['buy_stop']}")
    print(f"Sell Stop: {levels['sell_stop']}") 