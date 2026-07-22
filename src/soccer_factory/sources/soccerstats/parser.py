from bs4 import BeautifulSoup, Tag
from typing import List, Dict
from datetime import datetime
import uuid

from ..base import BaseParser
from ...schemas.matches import Match
from ...schemas.features import Features


class SoccerStatsParser(BaseParser):
    def __init__(self, version: str = "1.0"):
        self.version = version

    def parse_matches(self, content: bytes, collected_at: datetime) -> List[Match]:  # type: ignore[override]
        soup = BeautifulSoup(content, "lxml")
        matches: List[Match] = []

        table = soup.find("table", id="btable")
        if not table:
            return matches

        current_competition = "Unknown"

        for row in table.find_all("tr"):
            row_classes: list[str] = [c for c in (row.get("class") or []) if isinstance(c, str)]
            if "trow3" in row_classes:
                td = row.find("td")
                if td and td.b:
                    current_competition = td.b.text.strip()
                continue

            if "trow8" in row_classes:
                tds = row.find_all("td")
                if len(tds) < 5:
                    continue

                time_str: str = tds[0].text.strip()
                home_team: str = tds[1].text.strip()
                away_team: str = tds[3].text.strip()

                pmatch_link = ""
                a_tag = tds[4].find("a")
                if a_tag and "href" in a_tag.attrs:
                    href = a_tag["href"]
                    pmatch_link = href if isinstance(href, str) else str(href)

                status = "pre-match"
                if "P-P" in time_str:
                    status = "postponed"
                elif "'" in time_str or time_str == "HT":
                    status = "live"
                elif time_str == "FT":
                    status = "finished"

                kickoff = collected_at
                if status == "pre-match" and ":" in time_str:
                    try:
                        h, m = map(int, time_str.split(":"))
                        kickoff = collected_at.replace(hour=h, minute=m, second=0, microsecond=0)
                    except ValueError:
                        pass

                country = current_competition.split(" - ")[0] if " - " in current_competition else "Unknown"
                comp_key = current_competition.lower().replace(" ", "_")
                norm_home = home_team.lower()
                norm_away = away_team.lower()
                
                date_str = kickoff.strftime("%Y-%m-%d")
                time_str_kickoff = kickoff.strftime("%H:%M") if ":" in time_str else ""
                
                canonical_identity = f"match:soccer|{country}|{comp_key}||{date_str}|{time_str_kickoff}|{norm_home}|{norm_away}"
                deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, canonical_identity))

                match = Match(
                    match_id=deterministic_id,
                    sport="soccer",
                    country=country,
                    competition=current_competition,
                    competition_key=comp_key,
                    home_team=home_team,
                    away_team=away_team,
                    normalized_home_team=norm_home,
                    normalized_away_team=norm_away,
                    scheduled_kickoff=kickoff,
                    timezone="UTC",
                    source_urls={"soccerstats": pmatch_link},
                    status=status,
                    identity_confidence=1.0,
                    created_at=collected_at,
                    updated_at=collected_at,
                )
                matches.append(match)

        return matches

    def parse_predictions(self, content: bytes, collected_at: datetime) -> list[object]:
        return []

    def parse_features(self, content: bytes, match_id: str, collected_at: datetime) -> List[Features]:
        soup = BeautifulSoup(content, "lxml")
        features: List[Features] = []

        tables = soup.find_all("table", class_="sortable")
        if len(tables) < 2:
            return features

        home_table = tables[0]
        away_table = tables[1]

        def extract_stats(table: Tag) -> Dict[str, float]:
            stats: Dict[str, float] = {}
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) == 2:
                    key = tds[0].text.strip()
                    val = tds[1].text.strip().replace("%", "")
                    try:
                        stats[key] = float(val)
                    except ValueError:
                        pass
            return stats

        home_stats = extract_stats(home_table)
        away_stats = extract_stats(away_table)

        if not home_stats or not away_stats:
            return features

        f = Features(
            match_id=match_id,
            collected_at=collected_at,
            feature_cutoff=collected_at,
            match_kickoff=collected_at,
            data_type="pre-match",
            source_status="pre-match",
            home_goals_scored_avg=home_stats.get("GF", 0.0),
            home_goals_conceded_avg=home_stats.get("GA", 0.0),
            away_goals_scored_avg=away_stats.get("GF", 0.0),
            away_goals_conceded_avg=away_stats.get("GA", 0.0),
            btts_rate_home=home_stats.get("BTS", 0.0) / 100.0,
            btts_rate_away=away_stats.get("BTS", 0.0) / 100.0,
            over_25_rate_home=home_stats.get("2.5+", 0.0) / 100.0,
            over_25_rate_away=away_stats.get("2.5+", 0.0) / 100.0,
            home_ppg=home_stats.get("PPG", 0.0),
            away_ppg=away_stats.get("PPG", 0.0),
            sample_size_home=int(home_stats.get("GP", 0.0)),
            sample_size_away=int(away_stats.get("GP", 0.0)),
        )
        features.append(f)
        return features
