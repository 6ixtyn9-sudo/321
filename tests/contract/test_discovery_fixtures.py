import pytest
from src.soccer_factory.discovery.crawler import BoundedCrawler
from src.soccer_factory.discovery.models import DiscoveryConfig

@pytest.fixture
def ss_config():
    return DiscoveryConfig(
        max_depth=2,
        fixture_map_soccerstats={
            "https://www.soccerstats.com/matches.asp": "soccerstats/matches_today.html",
            "https://www.soccerstats.com/matches.asp?matchday=0&daym=yesterday&matchdayn=1": "soccerstats/matches_yesterday.html",
            "https://www.soccerstats.com/matches.asp?matchday=1&matchdayn=1": "soccerstats/matches_today.html",
            "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=1": "soccerstats/matches_tomorrow.html",
            "https://www.soccerstats.com/leagues.asp": "soccerstats/leagues.html",
            "https://www.soccerstats.com/stats.asp": "soccerstats/stats_page1.html",
            "https://www.soccerstats.com/faq.asp": "soccerstats/faq.html",
            "https://www.soccerstats.com/round_details.asp?league=ecuador&mrevid=m160&st1=13&st2=16": "soccerstats/round_details_example.html",
            "https://www.soccerstats.com/round_details.asp": "soccerstats/round_details_rich.html",
            "https://www.soccerstats.com/leagueview_team.asp": "soccerstats/leagueview_team.html",
            "https://www.soccerstats.com/stats.asp?page=10": "soccerstats/stats_page10.html",
            "https://www.soccerstats.com/homeaway.asp": "soccerstats/homeaway.html",
            "https://www.soccerstats.com/formtable.asp": "soccerstats/formtable.html",
            "https://www.soccerstats.com/table.asp?type=projected": "soccerstats/table_projection.html",
            "https://www.soccerstats.com/trends.asp": "soccerstats/trends.html",
            "https://www.soccerstats.com/teamstats.asp": "soccerstats/teamstats.html",
            "https://www.soccerstats.com/latest.asp": "soccerstats/latest.html",
            "https://www.soccerstats.com/pmatch.asp": "soccerstats/pmatch.html",
            "https://www.soccerstats.com/leagueview.asp": "soccerstats/leagueview.html"
        }
    )

@pytest.fixture
def fb_config():
    return DiscoveryConfig(
        max_depth=2,
        fixture_map_forebet={
            "https://www.forebet.com/en/football-tips-and-predictions-for-today": "forebet/daily_predictions.html",
            "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow": "forebet/tomorrow_predictions.html",
            "https://www.forebet.com/en/football-tips-and-predictions-for-the-weekend": "forebet/weekend_predictions.html",
            "https://www.forebet.com/en/football-predictions-from-yesterday": "forebet/finished_predictions.html",
            "https://www.forebet.com/en/live-football-tips": "forebet/live_predictions.html",
            "https://www.forebet.com/en/football/matches/atletico-mineiro-bahia-2418076": "forebet/football_match.html",
            "https://www.forebet.com/en/football-match-previews": "forebet/match_preview_index.html",
            "https://www.forebet.com/en/football-match-previews/28554-atletico-mineiro-seek-home-edge-against-bahia-in-tricky-brasileiro-serie-a-clash": "forebet/match_preview_article.html",
            "https://www.forebet.com/en/trends": "forebet/trends.html",
            "https://www.forebet.com/en/trends/top": "forebet/top_trends.html",
            "https://www.forebet.com/en/livescore": "forebet/livescore.html",
            "https://www.forebet.com/en/injured-players": "forebet/injured_players.html",
            "https://www.forebet.com/en/team-comparison": "forebet/team_comparison.html",
            "https://www.forebet.com/en/teams/some-team": "forebet/team_page.html",
            "https://www.forebet.com/en/prediction-lists": "forebet/prediction_list.html"
        }
    )

def test_soccerstats_fixture_mode(ss_config):
    crawler = BoundedCrawler(config=ss_config)
    seeds = [
        "https://www.soccerstats.com/matches.asp",
        "https://www.soccerstats.com/round_details.asp?league=ecuador&mrevid=m160&st1=13&st2=16",
        "https://www.soccerstats.com/round_details.asp",
        "https://www.soccerstats.com/leagueview_team.asp",
        "https://www.soccerstats.com/stats.asp?page=10",
        "https://www.soccerstats.com/homeaway.asp",
        "https://www.soccerstats.com/formtable.asp",
        "https://www.soccerstats.com/table.asp?type=projected",
        "https://www.soccerstats.com/trends.asp",
        "https://www.soccerstats.com/teamstats.asp",
        "https://www.soccerstats.com/latest.asp",
        "https://www.soccerstats.com/pmatch.asp",
        "https://www.soccerstats.com/leagueview.asp"
    ]
    
    entries, manifest = crawler.crawl("soccerstats", seeds, mode="fixture")
    assert manifest.pages_failed == 0
    
    found_families = set(e.page_family for e in entries if e.page_family != "unknown")
    
    # Check that we parsed all expected families from the seeds and links inside them
    assert "round_details" in found_families
    assert "leagueview_team" in found_families
    assert "home_away" in found_families
    assert "form_table" in found_families
    assert "projected_points" in found_families
    assert "trends" in found_families
    assert "team_stats" in found_families
    assert "league_latest" in found_families
    assert "match_preview" in found_families
    assert "league_view" in found_families

def test_forebet_fixture_mode(fb_config):
    crawler = BoundedCrawler(config=fb_config)
    seeds = [
        "https://www.forebet.com/en/football-tips-and-predictions-for-today",
        "https://www.forebet.com/en/football/matches/atletico-mineiro-bahia-2418076",
        "https://www.forebet.com/en/football-match-previews",
        "https://www.forebet.com/en/football-match-previews/28554-atletico-mineiro-seek-home-edge-against-bahia-in-tricky-brasileiro-serie-a-clash",
        "https://www.forebet.com/en/trends",
        "https://www.forebet.com/en/trends/top",
        "https://www.forebet.com/en/livescore",
        "https://www.forebet.com/en/injured-players",
        "https://www.forebet.com/en/team-comparison",
        "https://www.forebet.com/en/teams/some-team",
        "https://www.forebet.com/en/prediction-lists"
    ]
    
    entries, manifest = crawler.crawl("forebet", seeds, mode="fixture")
    assert manifest.pages_failed == 0
    
    found_families = set(e.page_family for e in entries if e.page_family != "unknown")
    
    assert "daily_predictions" in found_families
    assert "football_match" in found_families
    assert "match_preview_index" in found_families
    assert "match_preview_article" in found_families
    assert "trends" in found_families
    assert "top_trends" in found_families
    assert "livescore" in found_families
    assert "injured_players" in found_families
    assert "team_comparison" in found_families
    assert "team_page" in found_families
    assert "prediction_list" in found_families
