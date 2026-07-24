"""Forebet JSON client — hits ``/scripts/getrs.php`` with the required headers
and merges market responses into one wide record per match.

Bypasses HTML entirely (the HTML shell renders ``div.rcnt`` client-side from this
same JSON feed, so plain HTTP requests without a browser work once the proper
``Referer`` and ``X-Requested-With`` headers are set).
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from .urls import MARKETS, core_markets, daily_market_urls, json_headers, predictions_html_url


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return x if x == x else None  # NaN guard
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _day_slug(target: date, local_today: date) -> str:
    """Forebet's URL slug used for Referer (today / tomorrow / YYYY-MM-DD)."""
    delta = (target - local_today).days
    if delta == -1:
        return "yesterday"
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return target.isoformat()


def fetch_day(
    target: date,
    *,
    markets: Optional[List[str]] = None,
    local_today: Optional[date] = None,
    session: Optional[requests.Session] = None,
    retries: int = 3,
    sleep_between: float = 0.3,
    timeout: float = 20.0,
) -> List[Dict[str, Any]]:
    """Fetch one calendar day across the requested markets and merge into one
    record per match id.

    Each record contains (at minimum)::

        {
          "id": "2428078",
          "date": "2026-07-24",
          "kickoff_utc": datetime(...),  # parsed DATE_BAH as UTC
          "league_id": "144",
          "league_country": "Ecuador",
          "league_name": "Serie A",
          "league_slug": "football-tips-and-predictions-for-ecuador/serie-a",
          "country_code": "ec",
          "home": "CS Emelec",
          "away": "Mushuc Runa",
          "home_short": "CSE",
          "away_short": "MUS",
          "home_pos": "8th",
          "away_pos": "12th",
          "home_form": ["l","w","d","d","w","w"],
          "away_form": ["w","l","l","w","d","d"],
          "home_score": 1,            # FT, only when status==finished
          "away_score": 1,
          "home_score_ht": 1,
          "away_score_ht": 0,
          "pred_home_score": 2,       # forebet's predicted FT score
          "pred_away_score": 1,
          "status": "finished",       # pre-match | live | finished | postponed
          "status_raw": "FT",
          "round": "21",
          "is_cup": False,
          "stadium": "Estadio Banco del Pacífico",
          "weather_code": "11",
          "weather_high_f": 81,
          "probs": {
            "home": 0.45, "draw": 0.34, "away": 0.21,
            "over_25": ..., "under_25": ...,
            "btts_yes": ..., "btts_no": ...,
            "ht_home": ..., "ht_draw": ..., "ht_away": ...,
            "ah_type": "-0.5", "ah_home": ..., "ah_away": ...,
            ...
          },
          "odds": {
            "home": ..., "draw": ..., "away": ...,
            "over_25": ..., "under_25": ...,
            "btts_yes": ..., "btts_no": ...,
            ...
          },
          "source_url": "https://www.forebet.com/en/football-tips-and-predictions-for-...",
        }
    """
    if local_today is None:
        local_today = datetime.now(timezone.utc).date()
    if markets is None:
        markets = core_markets()

    day_slug = _day_slug(target, local_today)
    date_str = target.isoformat()

    sess = session or requests.Session()
    headers = json_headers(referer_day=day_slug)
    # Warm a Referer by hitting the HTML shell (some UAs get challenged otherwise)
    try:
        sess.get(predictions_html_url(day_slug), headers=headers, timeout=timeout)
    except Exception:
        pass

    rows_by_id: Dict[str, Dict[str, Any]] = {}
    meta: Dict[str, list] = {}

    for market_name, url in daily_market_urls(date_str, markets):
        tp = MARKETS[market_name][0]
        data = _get_with_retry(sess, url, headers, retries=retries, timeout=timeout, sleep=sleep_between)
        if not isinstance(data, list) or not data:
            continue
        market_rows = data[0] if isinstance(data[0], list) else []
        if len(data) > 1 and isinstance(data[1], dict):
            meta.update(data[1])
        for m in market_rows:
            mid = str(m.get("id"))
            if not mid:
                continue
            rec = rows_by_id.setdefault(mid, {
                "id": mid,
                "date": date_str,
                "kickoff_utc": None,
                "league_id": str(m.get("league_id") or ""),
                "league_country": None,
                "league_name": None,
                "league_slug": None,
                "country_code": (m.get("code") or "").lower() or None,
                "home": m.get("HOST_NAME") or "",
                "away": m.get("GUEST_NAME") or "",
                "home_short": m.get("host_short") or None,
                "away_short": m.get("guest_short") or None,
                "home_pos": m.get("host_pos") or None,
                "away_pos": m.get("guest_pos") or None,
                "home_form": m.get("host_form") or None,
                "away_form": m.get("guest_form") or None,
                "home_score": None,
                "away_score": None,
                "home_score_ht": None,
                "away_score_ht": None,
                "pred_home_score": None,
                "pred_away_score": None,
                "status": "pre-match",
                "status_raw": m.get("comment") or "",
                "round": m.get("Round") or None,
                "is_cup": str(m.get("isCup", "0")) == "1",
                "is_international_cup": str(m.get("is_international_club_cup", "0")) == "1",
                "stadium": m.get("host_stadium") or m.get("match_stadium"),
                "weather_code": m.get("weather_code"),
                "weather_high_f": _i(m.get("weather_temp_f")),
                "goals_avg": _f(m.get("goalsavg")),
                "probs": {},
                "odds": {},
                "source_url": None,
            })
            # Refresh base fields (in case a later market has better coverage)
            if m.get("HOST_NAME"):
                rec["home"] = m["HOST_NAME"]
            if m.get("GUEST_NAME"):
                rec["away"] = m["GUEST_NAME"]
            # Scores / predicted scores / status are canonical on 1x2 (carried on all
            # responses but 1x2 is the most complete)
            hs, gs = _i(m.get("Host_SC")), _i(m.get("Guest_SC"))
            if hs is not None:
                rec["home_score"] = hs
            if gs is not None:
                rec["away_score"] = gs
            hht, ght = _i(m.get("Host_SC_HT")), _i(m.get("Guest_SC_HT"))
            if hht is not None:
                rec["home_score_ht"] = hht
            if ght is not None:
                rec["away_score_ht"] = ght
            phs, pgs = _i(m.get("host_sc_pr")), _i(m.get("guest_sc_pr"))
            if phs is not None:
                rec["pred_home_score"] = phs
            if pgs is not None:
                rec["pred_away_score"] = pgs
            comment = (m.get("comment") or "").strip()
            if comment:
                rec["status_raw"] = comment
                low = comment.lower()
                if low in {"ft", "full-time", "full time", "aet"}:
                    rec["status"] = "finished"
                elif low in {"ht", "half-time", "half time"} or (comment.endswith("'") and comment[:-1].isdigit()):
                    rec["status"] = "live"
                elif low in {"postp.", "pp.", "p-p", "postponed", "susp.", "abn."}:
                    rec["status"] = "postponed"
                else:
                    rec["status"] = "pre-match"
            # Kickoff: DATE_BAH is "YYYY-MM-DD HH:MM:SS" in UTC
            date_bah = m.get("DATE_BAH")
            if date_bah and rec["kickoff_utc"] is None:
                try:
                    rec["kickoff_utc"] = datetime.strptime(date_bah, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            # market-specific probabilities and odds
            if market_name == "1x2":
                rec["probs"].update({k: _pct(m.get(k2)) for k, k2 in [
                    ("home", "Pred_1"), ("draw", "Pred_X"), ("away", "Pred_2"),
                ] if m.get(k2) is not None})
                rec["odds"].update({k: _f(m.get(k2)) for k, k2 in [
                    ("home", "best_odd_1"), ("draw", "best_odd_X"), ("away", "best_odd_2"),
                ] if m.get(k2) is not None})
                if m.get("kelly") is not None:
                    rec["kelly"] = _f(m.get("kelly"))
            elif market_name == "uo":
                rec["probs"].update({k: _pct(m.get(k2)) for k, k2 in [
                    ("over_25", "pr_over"), ("under_25", "pr_under"),
                ] if m.get(k2) is not None})
                rec["odds"].update({k: _f(m.get(k2)) for k, k2 in [
                    ("over_25", "best_over"), ("under_25", "best_under"),
                ] if m.get(k2) is not None})
            elif market_name == "bts":
                rec["probs"].update({k: _pct(m.get(k2)) for k, k2 in [
                    ("btts_yes", "Pred_gg"), ("btts_no", "Pred_no_gg"),
                ] if m.get(k2) is not None})
                rec["odds"].update({k: _f(m.get(k2)) for k, k2 in [
                    ("btts_yes", "odds_gg_y"), ("btts_no", "odds_gg_n"),
                ] if m.get(k2) is not None})
            elif market_name == "ht":
                rec["probs"].update({k: _pct(m.get(k2)) for k, k2 in [
                    ("ht_home", "Pred_1_HT"), ("ht_draw", "Pred_X_HT"), ("ht_away", "Pred_2_HT"),
                ] if m.get(k2) is not None})
                # HT best odds live under best_odd_ht
                for k, k2 in [("ht_home", "best_odd_ht"), ("ht_draw", "best_odd_ht"), ("ht_away", "best_odd_ht")]:
                    pass  # ht odds are aggregate; leave out for simplicity
            elif market_name == "htft":
                # Combined HT/FT odds under odds_htft - list keyed 1/1, X/1, etc.
                if m.get("odds_htft") is not None:
                    rec["odds"]["htft"] = m.get("odds_htft")
            elif market_name == "ah":
                ah_type = m.get("AH_type")
                if ah_type is not None:
                    rec["ah_line"] = ah_type
                rec["probs"].update({k: _pct(m.get(k2)) for k, k2 in [
                    ("ah_home", "Pred_1"), ("ah_away", "Pred_2"),
                ] if m.get(k2) is not None})
                if m.get("predAH") is not None:
                    rec["probs"]["ah_pred"] = m.get("predAH")
                if m.get("odds_ah") is not None:
                    rec["odds"]["ah"] = _f(m.get("odds_ah"))
            elif market_name == "corners":
                # Corner predictions reuse the 1X2 shape (over/under a corner line)
                rec["probs"]["corners_home"] = _pct(m.get("Pred_1"))
                rec["probs"]["corners_draw"] = _pct(m.get("Pred_X"))
                rec["probs"]["corners_away"] = _pct(m.get("Pred_2"))
            elif market_name == "cards":
                rec["probs"].update({k: _f(m.get(k2)) for k, k2 in [
                    ("cards_home_pred", "host_card_pred"),
                    ("cards_away_pred", "guest_card_pred"),
                    ("cards_line", "pred_line"),
                    ("cards_avg", "avg_cards"),
                ] if m.get(k2) is not None})
        time.sleep(sleep_between)

    # Resolve league metadata from meta
    for rec in rows_by_id.values():
        league_id = rec["league_id"]
        info = meta.get(league_id)
        if isinstance(info, (list, tuple)) and len(info) >= 3:
            rec["league_country"] = info[0] or None
            rec["league_name"] = info[1] or None
            rec["league_slug"] = info[2] or None
            if len(info) >= 6 and info[5]:
                rec["country_code"] = (rec["country_code"] or str(info[5]).lower())
        # Derive competition string: "<Country> - <League>" or "<League>" for intl
        if rec["league_country"] and rec["league_name"]:
            if rec["league_country"]:
                rec["competition"] = f"{rec['league_country']} - {rec['league_name']}"
            else:
                rec["competition"] = rec["league_name"]
        else:
            rec["competition"] = rec["league_name"] or "Unknown"
        if rec["league_slug"]:
            rec["source_url"] = f"https://www.forebet.com/en/{rec['league_slug']}"
        else:
            rec["source_url"] = predictions_html_url(day_slug)

        # Derived double-chance probabilities (client-side, 1X=1+X, X2=X+2, 12=1+2)
        ph = rec["probs"].get("home")
        px = rec["probs"].get("draw")
        pa = rec["probs"].get("away")
        if ph is not None and px is not None and pa is not None:
            rec["probs"]["dc_1x"] = ph + px
            rec["probs"]["dc_x2"] = px + pa
            rec["probs"]["dc_12"] = ph + pa

    return list(rows_by_id.values())


def _pct(v: Any) -> Optional[float]:
    """Forebet expresses its percentages as integers 0..100 in the JSON."""
    x = _f(v)
    if x is None:
        return None
    return x / 100.0


def _get_with_retry(
    sess: requests.Session,
    url: str,
    headers: Dict[str, str],
    *,
    retries: int = 3,
    timeout: float = 20.0,
    sleep: float = 0.5,
) -> Any:
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = sess.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                try:
                    return resp.json()
                except json.JSONDecodeError as e:
                    last_err = e
            else:
                last_err = RuntimeError(f"HTTP {resp.status_code}")
        except Exception as e:
            last_err = e
        time.sleep(sleep * (attempt + 1))
    if last_err:
        # Don't raise; callers can tolerate missing markets
        return []
    return []
