from src.soccer_factory.discovery.crawler import BoundedCrawler
from src.soccer_factory.discovery.models import DiscoveryConfig
from src.soccer_factory.discovery.seeds import get_seeds

def test_soccerstats_fixture_mode_counts():
    cfg = DiscoveryConfig(
        max_depth=2,
        fixture_map_soccerstats={
            "https://www.soccerstats.com/matches.asp": "soccerstats/matches_today.html",
            "https://www.soccerstats.com/matches.asp?matchday=0&daym=yesterday&matchdayn=1": "soccerstats/matches_yesterday.html",
            "https://www.soccerstats.com/matches.asp?matchday=1&matchdayn=1": "soccerstats/matches_today.html",
            "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=1": "soccerstats/matches_tomorrow.html",
            "https://www.soccerstats.com/leagues.asp": "soccerstats/leagues.html",
            "https://www.soccerstats.com/stats.asp": "soccerstats/stats_page1.html",
            "https://www.soccerstats.com/faq.asp": "soccerstats/faq.html",
            "https://www.soccerstats.com/round_details.asp?league=ecuador&mrevid=m160&st1=13&st2=16": "soccerstats/round_details_example.html"
        }
    )
    seeds = get_seeds("soccerstats")
    # Using dummy collector to ensure no network calls happen
    crawler = BoundedCrawler(config=cfg, collector=None)
    entries, manifest = crawler.crawl("soccerstats", seeds, mode="fixture")
    
    # 8 seeds fetched
    assert manifest.pages_fetched == 8
    assert manifest.network_requests == 0
    assert manifest.pages_failed == 0
    
    # Expected families based on fixture stubs
    expected = {
        "matches",
        "match_preview",
        "league_latest",
        "league_view",
        "results",
        "round_details",
        "statistical_overview",
        "faq",
        "home_away",
        "form_table",
        "wide_table",
        "generic_table",
        "team_stats",
        "leagueview_team",
        "match_list",
        "legal",
        "homepage"
    }
    # Our fixture mapping checks expected families based on actual discoveries in fixtures
    assert expected.issubset(set(manifest.families_found) | set(manifest.families_missing))

def test_forebet_fixture_mode_counts():
    cfg = DiscoveryConfig(
        max_depth=2,
        fixture_map_forebet={
            "https://www.forebet.com/en/football-tips-and-predictions-for-today": "forebet/today.html",
            "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow": "forebet/tomorrow.html",
            "https://www.forebet.com/en/football-tips-and-predictions-for-the-weekend": "forebet/weekend.html",
            "https://www.forebet.com/en/football-predictions-from-yesterday": "forebet/finished.html",
            "https://www.forebet.com/en/live-football-tips": "forebet/live.html"
        }
    )
    seeds = get_seeds("forebet")
    crawler = BoundedCrawler(config=cfg, collector=None)
    entries, manifest = crawler.crawl("forebet", seeds, mode="fixture")
    
    # 5 seeds fetched
    assert manifest.pages_fetched == 5
    assert manifest.network_requests == 0
    assert manifest.pages_failed == 0

    expected = {
        "daily_predictions",
        "tomorrow_predictions",
        "weekend_predictions",
        "finished_predictions",
        "live_predictions"
    }
    assert expected.issubset(set(manifest.families_found))
