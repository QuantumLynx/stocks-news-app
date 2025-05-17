from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict # Combined imports


@dataclass
class Article:
    title: str
    link: str
    published_date: Optional[datetime]
    summary: Optional[str]
    source: str
    tickers: Optional[List[str]] = None
    ticker_prices: Optional[Dict[str, float]] = None
