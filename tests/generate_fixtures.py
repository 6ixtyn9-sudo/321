import os
import shutil

FIXTURES_DIR = "tests/fixtures"

if os.path.exists(FIXTURES_DIR):
    shutil.rmtree(FIXTURES_DIR)
os.makedirs(FIXTURES_DIR, exist_ok=True)

soccerstats_prematch = """
<html><body>
<table id="btable">
  <tr class="trow3"><td colspan="5"><b>England - Premier League</b></td></tr>
  <tr class="trow8">
    <td class="td-s1">15:00</td>
    <td class="td-s2">Manchester United</td>
    <td class="td-s3">-</td>
    <td class="td-s4">Arsenal</td>
    <td class="td-s5"><a href="pmatch.asp?league=england&matchid=123">Stats</a></td>
  </tr>
  <tr class="trow8">
    <td class="td-s1">17:30</td>
    <td class="td-s2">Chelsea</td>
    <td class="td-s3">-</td>
    <td class="td-s4">Liverpool</td>
    <td class="td-s5"><a href="pmatch.asp?league=england&matchid=124">Stats</a></td>
  </tr>
  <tr class="trow3"><td colspan="5"><b>Spain - La Liga</b></td></tr>
  <tr class="trow8">
    <td class="td-s1">20:00</td>
    <td class="td-s2">Real Madrid</td>
    <td class="td-s3">-</td>
    <td class="td-s4">Barcelona</td>
    <td class="td-s5"><a href="pmatch.asp?league=spain&matchid=125">Stats</a></td>
  </tr>
  <!-- Ambiguous case: Nottingham F. will be quarantined because fuzzy match isn't 1.0 but it's close -->
  <tr class="trow8">
    <td class="td-s1">21:00</td>
    <td class="td-s2">Nottingham F.</td>
    <td class="td-s3">-</td>
    <td class="td-s4">Everton</td>
    <td class="td-s5"><a href="pmatch.asp?league=england&matchid=126">Stats</a></td>
  </tr>
  <!-- Unmatched match -->
  <tr class="trow8">
    <td class="td-s1">22:00</td>
    <td class="td-s2">Unmatched Home</td>
    <td class="td-s3">-</td>
    <td class="td-s4">Unmatched Away</td>
    <td class="td-s5"><a href="pmatch.asp?league=england&matchid=127">Stats</a></td>
  </tr>
</table>
</body></html>
"""

soccerstats_live = """
<html><body>
<table id="btable">
  <tr class="trow3"><td colspan="5"><b>England - Premier League</b></td></tr>
  <tr class="trow8">
    <td class="td-s1"><font color="red">55'</font></td>
    <td class="td-s2">Manchester United</td>
    <td class="td-s3">1 - 0</td>
    <td class="td-s4">Arsenal</td>
    <td class="td-s5"><a href="pmatch.asp?league=england&matchid=123">Stats</a></td>
  </tr>
</table>
</body></html>
"""

soccerstats_postponed = """
<html><body>
<table id="btable">
  <tr class="trow3"><td colspan="5"><b>England - Premier League</b></td></tr>
  <tr class="trow8">
    <td class="td-s1">P-P</td>
    <td class="td-s2">Manchester United</td>
    <td class="td-s3">-</td>
    <td class="td-s4">Arsenal</td>
    <td class="td-s5"><a href="pmatch.asp?league=england&matchid=123">Stats</a></td>
  </tr>
</table>
</body></html>
"""

soccerstats_malformed = """
<html><body>
<table id="btable">
  <tr class="trow8">
    <!-- Missing columns entirely -->
    <td class="td-s1">15:00</td>
  </tr>
</table>
</body></html>
"""

soccerstats_pmatch_complete = """
<html><body>
<div class="six columns">
  <h2>Home matches</h2>
  <table class="sortable">
    <tbody>
      <tr><td>W%</td><td>60%</td></tr>
      <tr><td>FTS</td><td>10%</td></tr>
      <tr><td>CS</td><td>40%</td></tr>
      <tr><td>BTS</td><td>50%</td></tr>
      <tr><td>TG</td><td>2.8</td></tr>
      <tr><td>GF</td><td>1.9</td></tr>
      <tr><td>GA</td><td>0.9</td></tr>
      <tr><td>1.5+</td><td>80%</td></tr>
      <tr><td>2.5+</td><td>60%</td></tr>
      <tr><td>3.5+</td><td>30%</td></tr>
      <tr><td>PPG</td><td>2.10</td></tr>
    </tbody>
  </table>
</div>
<div class="six columns">
  <h2>Away matches</h2>
  <table class="sortable">
    <tbody>
      <tr><td>W%</td><td>50%</td></tr>
      <tr><td>FTS</td><td>20%</td></tr>
      <tr><td>CS</td><td>30%</td></tr>
      <tr><td>BTS</td><td>60%</td></tr>
      <tr><td>TG</td><td>2.5</td></tr>
      <tr><td>GF</td><td>1.5</td></tr>
      <tr><td>GA</td><td>1.0</td></tr>
      <tr><td>1.5+</td><td>70%</td></tr>
      <tr><td>2.5+</td><td>50%</td></tr>
      <tr><td>3.5+</td><td>20%</td></tr>
      <tr><td>PPG</td><td>1.80</td></tr>
    </tbody>
  </table>
</div>
</body></html>
"""

soccerstats_pmatch_missing = """
<html><body>
<!-- Missing tables entirely -->
<div class="six columns">
  <h2>Home matches</h2>
</div>
</body></html>
"""

forebet_predictions_today = """
<html><body>
<div class="schema">
    <div class="rcnt tr_0">
        <div class="date_m">2026-07-21 15:00</div>
        <div class="tnms">
            <span class="homeTeam" itemprop="homeTeam">Manchester United FC</span>
            <span class="awayTeam" itemprop="awayTeam">Arsenal FC</span>
        </div>
        <div class="predict"><span class="pr">1</span></div>
        <div class="fprc"><span>50</span><span>30</span><span>20</span></div>
        <div class="ex_sc"><span>2 - 1</span></div>
        <div class="uo"><span>Over 2.5</span></div>
        <div class="bts"><span>Yes</span></div>
    </div>
    <div class="rcnt tr_1">
        <div class="date_m">2026-07-21 17:30</div>
        <div class="tnms">
            <span class="homeTeam" itemprop="homeTeam">Chelsea</span>
            <span class="awayTeam" itemprop="awayTeam">Liverpool</span>
        </div>
        <div class="predict"><span class="pr">X</span></div>
        <div class="fprc"><span>33</span><span>34</span><span>33</span></div>
        <div class="ex_sc"><span>1 - 1</span></div>
        <div class="uo"><span>Under 2.5</span></div>
        <div class="bts"><span>Yes</span></div>
    </div>
    <div class="rcnt tr_0">
        <div class="date_m">2026-07-21 20:00</div>
        <div class="tnms">
            <span class="homeTeam" itemprop="homeTeam">Real Madrid</span>
            <span class="awayTeam" itemprop="awayTeam">Barcelona</span>
        </div>
        <!-- DC prediction present -->
        <div class="predict"><span class="pr">1X</span></div>
        <div class="fprc"><span>45</span><span>35</span><span>20</span></div>
        <div class="ex_sc"><span>1 - 0</span></div>
        <div class="uo"><span>Under 2.5</span></div>
        <div class="bts"><span>No</span></div>
    </div>
    <div class="rcnt tr_1">
        <div class="date_m">2026-07-21 21:00</div>
        <div class="tnms">
            <span class="homeTeam" itemprop="homeTeam">Nottingham Forest</span>
            <span class="awayTeam" itemprop="awayTeam">Everton</span>
        </div>
        <div class="predict"><span class="pr">2</span></div>
        <!-- Missing probability block -->
        <div class="fprc"></div>
        <div class="ex_sc"><span>0 - 1</span></div>
        <div class="uo"><span>Under 2.5</span></div>
        <div class="bts"><span>No</span></div>
    </div>
    <div class="rcnt tr_0">
        <div class="date_m">2026-07-21 22:30</div>
        <div class="tnms">
            <span class="homeTeam" itemprop="homeTeam">Forebet Unmatched Home</span>
            <span class="awayTeam" itemprop="awayTeam">Forebet Unmatched Away</span>
        </div>
        <div class="predict"><span class="pr">1</span></div>
        <div class="fprc"><span>60</span><span>20</span><span>20</span></div>
        <div class="ex_sc"><span>3 - 0</span></div>
        <div class="uo"><span>Over 2.5</span></div>
        <div class="bts"><span>No</span></div>
    </div>
</div>
</body></html>
"""

forebet_predictions_revised = """
<html><body>
<div class="schema">
    <div class="rcnt tr_0">
        <div class="date_m">2026-07-21 15:00</div>
        <div class="tnms">
            <span class="homeTeam" itemprop="homeTeam">Manchester United FC</span>
            <span class="awayTeam" itemprop="awayTeam">Arsenal FC</span>
        </div>
        <!-- Revised from 1 to X and different probs -->
        <div class="predict"><span class="pr">X</span></div>
        <div class="fprc"><span>35</span><span>35</span><span>30</span></div>
        <div class="ex_sc"><span>1 - 1</span></div>
        <div class="uo"><span>Under 2.5</span></div>
        <div class="bts"><span>Yes</span></div>
    </div>
</div>
</body></html>
"""

forebet_predictions_finished = """
<html><body>
<div class="schema">
    <div class="rcnt tr_0">
        <div class="date_m">2026-07-21 15:00</div>
        <div class="tnms">
            <span class="homeTeam" itemprop="homeTeam">Manchester United FC</span>
            <span class="awayTeam" itemprop="awayTeam">Arsenal FC</span>
        </div>
        <div class="predict"><span class="pr">1</span></div>
        <div class="fprc"><span>50</span><span>30</span><span>20</span></div>
        <div class="ex_sc"><span>2 - 1</span></div>
        <div class="l_scr"><span>2 - 1</span></div> <!-- Indicator of finished -->
        <div class="uo"><span>Over 2.5</span></div>
        <div class="bts"><span>Yes</span></div>
    </div>
</div>
</body></html>
"""

forebet_predictions_live = """
<html><body>
<div class="schema">
    <div class="rcnt tr_0">
        <div class="date_m">2026-07-21 15:00</div>
        <div class="tnms">
            <span class="homeTeam" itemprop="homeTeam">Manchester United FC</span>
            <span class="awayTeam" itemprop="awayTeam">Arsenal FC</span>
        </div>
        <div class="predict"><span class="pr">1</span></div>
        <div class="fprc"><span>50</span><span>30</span><span>20</span></div>
        <div class="ex_sc"><span>2 - 1</span></div>
        <div class="l_scr"><span>1 - 0</span></div> <!-- Live score -->
        <div class="live_min"><span>45'</span></div> <!-- Indicator of live -->
        <div class="uo"><span>Over 2.5</span></div>
        <div class="bts"><span>Yes</span></div>
    </div>
</div>
</body></html>
"""

forebet_predictions_malformed = """
<html><body>
<div class="schema">
    <div class="rcnt tr_0">
        <div class="date_m">2026-07-21 15:00</div>
        <!-- Missing tnms block entirely -->
        <div class="predict"><span class="pr">1</span></div>
    </div>
</div>
</body></html>
"""

def write(name, content):
    with open(f"{FIXTURES_DIR}/{name}", "w") as f:
        f.write(content.strip())

write("soccerstats_matches_prematch.html", soccerstats_prematch)
write("soccerstats_matches_live.html", soccerstats_live)
write("soccerstats_matches_postponed.html", soccerstats_postponed)
write("soccerstats_matches_malformed.html", soccerstats_malformed)
write("soccerstats_pmatch_complete.html", soccerstats_pmatch_complete)
write("soccerstats_pmatch_missing_stats.html", soccerstats_pmatch_missing)

write("forebet_predictions_today.html", forebet_predictions_today)
write("forebet_predictions_finished.html", forebet_predictions_finished)
write("forebet_predictions_live.html", forebet_predictions_live)
write("forebet_predictions_malformed.html", forebet_predictions_malformed)
write("forebet_predictions_revised.html", forebet_predictions_revised)

print("Fixtures created successfully.")
