"""Parsers for Forebet daily tips and market pages.

PATCHED VERSION (2.2-json):
- Primary path parses the JSON feed returned by ``/scripts/getrs.php`` (the exact
  payload the site's JS uses to render every market tab).  The HTML shell at
  ``/en/football-tips-and-predictions-for-<day>`` renders client-side and so
  ``div.rcnt`` rows are empty for non-browser HTTP clients; the JSON endpoint
  responds to plain requests once the right ``Referer`` + ``X-Requested-With``
  headers are sent.
- Falls back to the legacy HTML parser for snapshot HTML that happens to
  already contain rendered ``div.rcnt`` rows (fixture files, Playwright runs).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base import BaseParser
from ...schemas.matches import Match
from ...schemas.predictions import Market, SourceObservation


class ForebetParser(BaseParser):
    def __init__(self, version: str = "2.2-json"):
        self.version = version

    # ------------------------------------------------------------------
    # JSON feed -> Match / SourceObservation
    # ------------------------------------------------------------------
    def matches_from_records(self, records: Iterable[Dict[str, Any]], collected_at: datetime) -> List[Match]:
        out: List[Match] = []
        for rec in records:
            kickoff = rec.get("kickoff_utc") or collected_at
            home = rec.get("home") or ""
            away = rec.get("away") or ""
            if not home or not away:
                continue
            competition = rec.get("competition") or "Unknown"
            country = rec.get("league_country") or "Unknown"
            # Stable canonical: source | league | date | norm home | norm away
            canon_parts = [
                "match:forebet",
                str(rec.get("league_id") or ""),
                (rec.get("date") or kickoff.date().isoformat()),
                _norm(home), _norm(away),
            ]
            canonical = "|".join(canon_parts)
            out.append(Match(
                match_id=str(uuid.uuid5(uuid.NAMESPACE_URL, canonical)),
                sport="soccer",
                country=country or "Unknown",
                competition=competition,
                competition_key=_comp_key(competition),
                home_team=home,
                away_team=away,
                normalized_home_team=_norm(home),
                normalized_away_team=_norm(away),
                scheduled_kickoff=kickoff,
                timezone="UTC",
                source_urls={"forebet": rec.get("source_url") or "https://www.forebet.com/"},
                status=rec.get("status", "pre-match"),
                identity_confidence=0.95 if rec.get("source_url") else 0.7,
                created_at=collected_at,
                updated_at=collected_at,
            ))
        return out

    def observations_from_records(self, records: Iterable[Dict[str, Any]], collected_at: datetime) -> List[SourceObservation]:
        out: List[SourceObservation] = []
        for rec in records:
            home = rec.get("home") or ""
            away = rec.get("away") or ""
            if not home or not away:
                continue
            match_id = f"{home} vs {away}"
            status = rec.get("status", "pre-match")
            probs = rec.get("probs") or {}
            odds = rec.get("odds") or {}
            pred_hs = rec.get("pred_home_score")
            pred_gs = rec.get("pred_away_score")
            pred_score = f"{pred_hs}:{pred_gs}" if pred_hs is not None and pred_gs is not None else None

            def add(market: str, selection: str, prob: Optional[float]) -> None:
                if prob is None:
                    return
                out.append(SourceObservation(
                    source="forebet",
                    match_identity=match_id,
                    market=market,
                    selection=selection,
                    predicted_score=pred_score,
                    probability_if_present=prob,
                    source_status=status,
                    collected_at=collected_at,
                    source_url=rec.get("source_url") or "https://www.forebet.com/",
                    parser_version=self.version,
                    is_pre_match=(status == "pre-match"),
                    is_live=(status == "live"),
                    is_finished=(status == "finished"),
                ))

            # 1X2 (from Pred_1/X/2) + pick the max-probability tip as the main pick
            p1, px, p2 = probs.get("home"), probs.get("draw"), probs.get("away")
            if p1 is not None or px is not None or p2 is not None:
                if p1 is not None:
                    add(Market.RESULT_1X2.value, "1", p1)
                if px is not None:
                    add(Market.RESULT_1X2.value, "X", px)
                if p2 is not None:
                    add(Market.RESULT_1X2.value, "2", p2)
                # "Pick of the day" selection = argmax
                triple = [(p1, "1"), (px, "X"), (p2, "2")]
                triple = [(p, s) for p, s in triple if p is not None]
                if triple:
                    best_p, best_s = max(triple, key=lambda x: x[0])
                    add("forebet_pick", best_s, best_p)

            # Double chance (derived client-side)
            for sel, key in (("1X", "dc_1x"), ("X2", "dc_x2"), ("12", "dc_12")):
                p = probs.get(key)
                add(Market.DOUBLE_CHANCE.value, sel, p)

            # Over / Under 2.5 goals
            po, pu = probs.get("over_25"), probs.get("under_25")
            if po is not None:
                add(Market.OVER_25.value, "Over 2.5", po)
            if pu is not None:
                add(Market.OVER_25.value, "Under 2.5", pu)

            # BTTS
            py, pn = probs.get("btts_yes"), probs.get("btts_no")
            if py is not None:
                add(Market.BTTS.value, "Yes", py)
            if pn is not None:
                add(Market.BTTS.value, "No", pn)

            # Half-time result
            for sel, key in (("1", "ht_home"), ("X", "ht_draw"), ("2", "ht_away")):
                p = probs.get(key)
                if p is not None:
                    add(Market.HT_FT.value, f"HT/{sel}", p)

            # Asian handicap (probabilities only - schema has no ASIAN_HANDICAP
            # market, so emit under a custom market name)
            if "ah_line" in rec:
                add("asian_handicap",
                    f"Home {rec['ah_line']}",
                    probs.get("ah_home"))
                add("asian_handicap",
                    f"Away {-float(rec['ah_line']) if _isnum(rec['ah_line']) else ''}",
                    probs.get("ah_away"))

            # Corners (probabilities only)
            if probs.get("corners_home") is not None:
                add("corners", "home", probs.get("corners_home"))
                add("corners", "draw", probs.get("corners_draw"))
                add("corners", "away", probs.get("corners_away"))

            # Cards (line + projections only - no probability selection)
            # Skip emitting observations with no probability/selection support.

            # Predicted score already captured via pred_score on the 1X2 obs.
        return out

    # ------------------------------------------------------------------
    # Public API (BaseParser interface)
    # ------------------------------------------------------------------
    def parse_matches(self, content: bytes, collected_at: datetime) -> List[Match]:
        """If ``content`` is a Forebet JSON byte string, parse it directly;
        otherwise fall back to HTML scraping of rendered ``div.rcnt``."""
        text = content[:200].lstrip()
        if text.startswith(b"[") or text.startswith(b"{"):
            try:
                import json
                data = json.loads(content.decode("utf-8", "replace"))
                records = _records_from_json_payload(data)
                if records:
                    return self.matches_from_records(records, collected_at)
            except Exception:
                pass
        return self._parse_html_matches(content, collected_at)

    def parse_predictions(self, content: bytes, collected_at: datetime) -> List[SourceObservation]:
        text = content[:200].lstrip()
        if text.startswith(b"[") or text.startswith(b"{"):
            try:
                import json
                data = json.loads(content.decode("utf-8", "replace"))
                records = _records_from_json_payload(data)
                if records:
                    return self.observations_from_records(records, collected_at)
            except Exception:
                pass
        return self._parse_html_observations(content, collected_at)

    # ------------------------------------------------------------------
    # Legacy HTML fallback (Playwright-rendered / fixture HTML)
    # ------------------------------------------------------------------
    def _parse_html_matches(self, content: bytes, collected_at: datetime) -> List[Match]:
        soup = BeautifulSoup(content, "lxml")
        matches: List[Match] = []
        for row in soup.find_all("div", class_="rcnt"):
            tnms = row.find("div", class_="tnms")
            if not tnms:
                continue
            home = tnms.find("span", class_="homeTeam")
            away = tnms.find("span", class_="awayTeam")
            if not home or not away:
                continue
            home_team, away_team = home.text.strip(), away.text.strip()
            date_div = row.find("div", class_="date_m")
            date_str = date_div.text.strip() if date_div else ""
            status = "pre-match"
            if row.find("div", class_="l_scr"):
                if row.find("div", class_="live_min"):
                    status = "live"
                else:
                    status = "finished"
            kickoff = collected_at
            if date_str:
                try:
                    kickoff = datetime.strptime(date_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            canonical = "|".join(("match:forebet", "unknown", kickoff.date().isoformat(),
                                   _norm(home_team), _norm(away_team)))
            matches.append(Match(
                match_id=str(uuid.uuid5(uuid.NAMESPACE_URL, canonical)),
                sport="soccer", country="Unknown", competition="Unknown",
                competition_key="unknown", home_team=home_team, away_team=away_team,
                normalized_home_team=_norm(home_team), normalized_away_team=_norm(away_team),
                scheduled_kickoff=kickoff, timezone="UTC", source_urls={}, status=status,
                identity_confidence=0.7, created_at=collected_at, updated_at=collected_at,
            ))
        return matches

    def _parse_html_observations(self, content: bytes, collected_at: datetime) -> List[SourceObservation]:
        soup = BeautifulSoup(content, "lxml")
        obs: List[SourceObservation] = []
        for row in soup.find_all("div", class_="rcnt"):
            tnms = row.find("div", class_="tnms")
            if not tnms:
                continue
            home = tnms.find("span", class_="homeTeam")
            away = tnms.find("span", class_="awayTeam")
            if not home or not away:
                continue
            match_id = f"{home.text.strip()} vs {away.text.strip()}"
            status = "pre-match"
            if row.find("div", class_="l_scr"):
                status = "live" if row.find("div", class_="live_min") else "finished"
            predict_div = row.find("div", class_="predict")
            selection = predict_div.text.strip() if predict_div else None
            market = Market.RESULT_1X2.value
            if selection in {"1X", "X2", "12"}:
                market = Market.DOUBLE_CHANCE.value
            elif selection not in {"1", "X", "2"}:
                selection = None
            score_div = row.find("div", class_="ex_sc")
            predicted_score = score_div.text.strip() if score_div else None
            prob = None
            fprc = row.find("div", class_="fprc")
            if fprc and selection:
                spans = fprc.find_all("span")
                if len(spans) == 3:
                    try:
                        p1, px, p2 = [float(s.text.strip()) / 100.0 for s in spans]
                        prob = {"1": p1, "X": px, "2": p2, "1X": p1+px, "X2": px+p2, "12": p1+p2}.get(selection)
                    except ValueError:
                        pass
            if selection:
                obs.append(SourceObservation(
                    source="forebet", match_identity=match_id, market=market,
                    selection=selection, predicted_score=predicted_score,
                    probability_if_present=prob, source_status=status,
                    collected_at=collected_at, source_url="forebet.com",
                    parser_version=self.version,
                    is_pre_match=(status == "pre-match"), is_live=(status == "live"),
                    is_finished=(status == "finished"),
                ))
            uo_div = row.find("div", class_="uo")
            if uo_div and "2.5" in uo_div.text:
                obs.append(SourceObservation(
                    source="forebet", match_identity=match_id, market=Market.OVER_25.value,
                    selection=uo_div.text.strip(), predicted_score=predicted_score,
                    source_status=status, collected_at=collected_at, source_url="forebet.com",
                    parser_version=self.version,
                    is_pre_match=(status == "pre-match"), is_live=(status == "live"),
                    is_finished=(status == "finished"),
                ))
            btts_div = row.find("div", class_="bts")
            if btts_div and btts_div.text.strip() in {"Yes", "No"}:
                obs.append(SourceObservation(
                    source="forebet", match_identity=match_id, market=Market.BTTS.value,
                    selection=btts_div.text.strip(), predicted_score=predicted_score,
                    source_status=status, collected_at=collected_at, source_url="forebet.com",
                    parser_version=self.version,
                    is_pre_match=(status == "pre-match"), is_live=(status == "live"),
                    is_finished=(status == "finished"),
                ))
        return obs


def _records_from_json_payload(data: Any) -> List[Dict[str, Any]]:
    """The JSON endpoint always returns ``[rows, meta]``; accept both that shape
    and a bare list of rows."""
    if isinstance(data, list) and data and isinstance(data[0], list):
        return list(data[0])
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict) and "rows" in data:
        return list(data["rows"])
    return []


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _comp_key(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", v.lower()).strip("_")


def _isnum(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
