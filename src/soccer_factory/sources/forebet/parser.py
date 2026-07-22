from bs4 import BeautifulSoup
from typing import List
from datetime import datetime, timezone
import uuid

from ..base import BaseParser
from ...schemas.matches import Match
from ...schemas.predictions import SourceObservation, Market

class ForebetParser(BaseParser):
    def __init__(self, version: str = "1.0"):
        self.version = version

    def parse_matches(self, content: bytes, collected_at: datetime) -> List[Match]:  # type: ignore[override]
        soup = BeautifulSoup(content, 'lxml')
        matches = []
        
        for row in soup.find_all('div', class_='rcnt'):
            tnms = row.find('div', class_='tnms')
            if not tnms:
                continue
                
            home = tnms.find('span', class_='homeTeam')
            away = tnms.find('span', class_='awayTeam')
            if not home or not away:
                continue
                
            home_team = home.text.strip()
            away_team = away.text.strip()
            
            date_div = row.find('div', class_='date_m')
            date_str = date_div.text.strip() if date_div else ""
            
            status = "pre-match"
            if row.find('div', class_='l_scr'):
                if row.find('div', class_='live_min'):
                    status = "live"
                else:
                    status = "finished"
                    
            kickoff = collected_at
            if date_str:
                try:
                    kickoff = datetime.strptime(date_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            
            country = "Unknown"
            comp_key = "unknown"
            norm_home = home_team.lower()
            norm_away = away_team.lower()
            
            date_str_formatted = kickoff.strftime("%Y-%m-%d") if date_str else ""
            time_str_kickoff = kickoff.strftime("%H:%M") if date_str and ":" in date_str else ""
            
            canonical_identity = f"match:soccer|{country}|{comp_key}||{date_str_formatted}|{time_str_kickoff}|{norm_home}|{norm_away}"
            deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, canonical_identity))

            match = Match(
                match_id=deterministic_id,
                sport="soccer",
                country=country,
                competition="Unknown",
                competition_key=comp_key,
                home_team=home_team,
                away_team=away_team,
                normalized_home_team=norm_home,
                normalized_away_team=norm_away,
                scheduled_kickoff=kickoff,
                timezone="UTC",
                source_urls={},
                status=status,
                identity_confidence=1.0,
                created_at=collected_at,
                updated_at=collected_at
            )
            matches.append(match)
            
        return matches

    def parse_predictions(self, content: bytes, collected_at: datetime) -> List[SourceObservation]:  # type: ignore[override]
        soup = BeautifulSoup(content, 'lxml')
        observations = []
        
        for row in soup.find_all('div', class_='rcnt'):
            tnms = row.find('div', class_='tnms')
            if not tnms:
                continue
                
            home = tnms.find('span', class_='homeTeam')
            away = tnms.find('span', class_='awayTeam')
            if not home or not away:
                continue
                
            home_team = home.text.strip()
            away_team = away.text.strip()
            match_identity = f"{home_team} vs {away_team}"
            
            status = "pre-match"
            if row.find('div', class_='l_scr'):
                if row.find('div', class_='live_min'):
                    status = "live"
                else:
                    status = "finished"
                    
            predict_div = row.find('div', class_='predict')
            selection = predict_div.text.strip() if predict_div else None
            
            market = Market.RESULT_1X2.value
            if selection in ["1X", "X2", "12"]:
                market = Market.DOUBLE_CHANCE.value
            elif selection not in ["1", "X", "2"]:
                selection = None 
                
            score_div = row.find('div', class_='ex_sc')
            predicted_score = score_div.text.strip() if score_div else None
            
            prob = None
            fprc = row.find('div', class_='fprc')
            if fprc and selection:
                spans = fprc.find_all('span')
                if len(spans) == 3:
                    try:
                        p1, px, p2 = [float(s.text.strip()) / 100.0 for s in spans]
                        if selection == "1":
                            prob = p1
                        elif selection == "X":
                            prob = px
                        elif selection == "2":
                            prob = p2
                        elif selection == "1X":
                            prob = p1 + px
                        elif selection == "X2":
                            prob = px + p2
                        elif selection == "12":
                            prob = p1 + p2
                    except ValueError:
                        pass
                        
            if selection:
                observations.append(SourceObservation(
                    source="forebet",
                    match_identity=match_identity,
                    market=market,
                    selection=selection,
                    predicted_score=predicted_score,
                    probability_if_present=prob,
                    source_status=status,
                    collected_at=collected_at,
                    source_url="forebet.com",
                    parser_version=self.version,
                    is_pre_match=(status == "pre-match"),
                    is_live=(status == "live"),
                    is_finished=(status == "finished")
                ))
                
            uo_div = row.find('div', class_='uo')
            if uo_div:
                uo_text = uo_div.text.strip()
                if "2.5" in uo_text:
                    observations.append(SourceObservation(
                        source="forebet",
                        match_identity=match_identity,
                        market=Market.OVER_25.value,
                        selection=uo_text,
                        predicted_score=predicted_score,
                        probability_if_present=None,
                        source_status=status,
                        collected_at=collected_at,
                        source_url="forebet.com",
                        parser_version=self.version,
                        is_pre_match=(status == "pre-match"),
                        is_live=(status == "live"),
                        is_finished=(status == "finished")
                    ))
                    
            btts_div = row.find('div', class_='bts')
            if btts_div:
                btts_text = btts_div.text.strip()
                if btts_text in ["Yes", "No"]:
                    observations.append(SourceObservation(
                        source="forebet",
                        match_identity=match_identity,
                        market=Market.BTTS.value,
                        selection=btts_text,
                        predicted_score=predicted_score,
                        probability_if_present=None,
                        source_status=status,
                        collected_at=collected_at,
                        source_url="forebet.com",
                        parser_version=self.version,
                        is_pre_match=(status == "pre-match"),
                        is_live=(status == "live"),
                        is_finished=(status == "finished")
                    ))
                    
        return observations
