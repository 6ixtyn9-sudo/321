from ..http_collector import HttpCollector
from ..registry import register_collector

@register_collector("forebet")
class ForebetCollector(HttpCollector):
    def __init__(self, contact_email: str):
        user_agent = f"SoccerFactory/0.1 (+{contact_email})"
        super().__init__(user_agent=user_agent, delay=3.0, max_requests=50)
