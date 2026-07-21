import traceback
from soccer_factory.discovery import crawler

try:
    crawler.crawl("soccerstats", ["https://www.soccerstats.com/matches.asp"], mode="fixture")
except Exception:
    traceback.print_exc()
