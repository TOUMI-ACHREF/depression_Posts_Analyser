from src.scrapers.facebook_scraper import (
    scrape_and_store as scrape_facebook_and_store,
)
from src.scrapers.facebook_scraper import scrape_hashtag as scrape_facebook_hashtag
from src.scrapers.twitter_scraper import scrape_and_store, scrape_hashtag

__all__ = [
    "scrape_hashtag",
    "scrape_and_store",
    "scrape_facebook_hashtag",
    "scrape_facebook_and_store",
]

