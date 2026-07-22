import pytest
from src.soccer_factory.discovery.catalog import CatalogStore
from src.soccer_factory.discovery.models import CatalogEntry

def test_select_representatives(tmp_path):
    store = CatalogStore(catalog_dir=str(tmp_path))
    entry1 = CatalogEntry(
        source="soccerstats",
        url="https://www.soccerstats.com/matches.asp",
        canonical_url="https://www.soccerstats.com/matches.asp",
        page_family="matches",
        discovery_status="discovered",
        fetch_status="ok",
        http_status=200,
        links_found=10,
        data_fields_detected=["f1"]
    )
    store.append(entry1)
    
    # Second entry in same family with more links
    entry2 = CatalogEntry(
        source="soccerstats",
        url="https://www.soccerstats.com/matches.asp?test=1",
        canonical_url="https://www.soccerstats.com/matches.asp",
        page_family="matches",
        discovery_status="discovered",
        fetch_status="ok",
        http_status=200,
        links_found=20,
        data_fields_detected=["f1", "f2"]
    )
    store.append(entry2)
    
    reps = store.select_representatives("soccerstats")
    assert len(reps) > 0
    daily_rep = next(r for r in reps if r.family == "matches")
    assert daily_rep.example_url == entry2.url
    assert daily_rep.links_found == 20
    assert daily_rep.fields_found == 2
