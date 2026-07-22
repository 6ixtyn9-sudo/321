from src.soccer_factory.sources.soccerstats.results import extract_result_detail


def test_result_extraction_preserves_all_nonempty_table_rows():
    html = b"""<html><head><title>Match details</title></head><body>
    <h2>Result analysis</h2><table><tr><th>Metric</th><th>Home</th></tr>
    <tr><td>Final score</td><td>2</td></tr></table></body></html>"""
    extracted = extract_result_detail(html)
    assert extracted["page_title"] == "Match details"
    assert extracted["headings"] == ["Result analysis"]
    assert extracted["tables"] == [{"table_index": 1, "rows": [["Metric", "Home"], ["Final score", "2"]]}]
