import unicodedata
import re

def normalize_team_name(name: str) -> str:
    """Normalizes a team name for identity matching."""
    if not name:
        return ""
        
    # Lowercase
    name = name.lower()
    
    # Remove accents and diacritics
    name = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    
    # Remove punctuation
    name = re.sub(r'[^\w\s]', ' ', name)
    
    # Remove common suffixes/prefixes (FC, CF, SC, AFC, Rovers, Athletic, Real, Sporting, Club)
    # Note: City and United are NOT stopwords as they distinguish Manchester City/United.
    stop_words = {'fc', 'cf', 'sc', 'afc', 'rovers', 'athletic', 'real', 'sporting', 'club'}
    words = name.split()
    
    filtered_words = [w for w in words if w not in stop_words]
    
    if not filtered_words:
        # If all words were stop words, return the original stripped down name
        filtered_words = words
        
    # Handle U21, U23, B teams specifically so they don't map to senior teams
    # We leave them intact
    
    return ' '.join(filtered_words).strip()
