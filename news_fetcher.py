import feedparser
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from article import Article
from datetime import datetime
import time # For parsing dates
import yfinance as yf # Added yfinance
import re # For improved ticker matching
from colorama import init, Fore, Back, Style

# Initialize colorama
init(autoreset=True)

# Path to the sources configuration file
SOURCES_FILE = Path(__file__).parent / "sources.json"


def load_sources() -> List[Dict[str, Any]]:
    """Loads news sources from the JSON configuration file."""
    if not SOURCES_FILE.exists():
        print(f"{Fore.RED}Warning: Sources file not found at {SOURCES_FILE}{Style.RESET_ALL}")
        return []
    try:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            sources = json.load(f)
        return sources
    except json.JSONDecodeError as e:
        print(f"{Fore.RED}Error decoding JSON from {SOURCES_FILE}: {e}{Style.RESET_ALL}")
        return []
    except Exception as e:
        print(f"{Fore.RED}Error loading sources file {SOURCES_FILE}: {e}{Style.RESET_ALL}")
        return []


def fetch_articles_from_rss(feed_url: str, source_name: str) -> List[Article]:
    """Fetches and parses articles from an RSS feed."""
    articles: List[Article] = []
    print(f"{Fore.BLUE}Fetching from RSS: {Fore.CYAN}{feed_url}{Style.RESET_ALL}")
    try:
        # Add a user-agent to potentially avoid blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        feed_data = feedparser.parse(feed_url, agent=headers.get('User-Agent'))

        if feed_data.bozo:
            bozo_exception = feed_data.bozo_exception
            print(f"{Fore.YELLOW}Warning: Ill-formed feed from {feed_url}. Reason: {bozo_exception}{Style.RESET_ALL}")

        for entry in feed_data.entries:
            published_dt: Optional[datetime] = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    published_dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                except TypeError: # Handle cases where published_parsed might be None despite existing
                    pass 
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                try:
                    published_dt = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                except TypeError:
                    pass

            summary = getattr(entry, 'summary', None) or getattr(entry, 'description', None)
            
            article = Article(
                title=getattr(entry, 'title', 'N/A'),
                link=getattr(entry, 'link', 'N/A'),
                published_date=published_dt,
                summary=summary,
                source=source_name
            )
            articles.append(article)
    except Exception as e:
        print(f"{Fore.RED}Error fetching or parsing RSS feed from {feed_url}: {e}{Style.RESET_ALL}")
    return articles


def fetch_current_prices(ticker_symbols: List[str]) -> Dict[str, float]:
    """Fetches current prices for a list of stock tickers using yfinance."""
    prices: Dict[str, float] = {}
    if not ticker_symbols:
        return prices

    for symbol in ticker_symbols:
        try:
            ticker_obj = yf.Ticker(symbol)
            # Attempt to get current market price; fall back to previous close
            info = ticker_obj.info
            current_price = info.get('currentPrice') or \
                            info.get('regularMarketPrice') or \
                            info.get('previousClose') # Added previousClose as another fallback

            if current_price is None:
                # Fallback to history if not found in info (e.g. for some indices or less common tickers)
                hist = ticker_obj.history(period="2d") # Get 2 days to be safe
                if not hist.empty and 'Close' in hist.columns:
                    current_price = hist['Close'].iloc[-1]
            
            if current_price is not None:
                prices[symbol] = float(current_price)
                print(f"{Fore.GREEN}Fetched price for {Fore.YELLOW}{symbol}{Fore.GREEN}: {current_price}{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}Warning: Could not fetch price for {symbol} after multiple attempts.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Error fetching price for {symbol} with yfinance: {e}{Style.RESET_ALL}")
    return prices


def fetch_all_news(stock_symbols: Optional[List[str]] = None, source_limit: Optional[int] = None) -> List[Article]:
    """
    Fetches news from all configured sources.
    Filters by stock symbols if provided (case-insensitive search in title and summary).
    Optionally limits the number of sources processed.
    """
    all_articles: List[Article] = []
    sources = load_sources()

    if source_limit is not None and source_limit > 0:
        sources = sources[:source_limit]
        print(f"{Fore.CYAN}Limiting to first {len(sources)} source(s).{Style.RESET_ALL}")
    elif source_limit is not None and source_limit <= 0:
        print(f"{Fore.YELLOW}Warning: --source-limit is non-positive, processing all sources.{Style.RESET_ALL}")


    for source_config in sources:
        print(f"{Fore.MAGENTA}Processing source: {Fore.WHITE}{Style.BRIGHT}{source_config.get('name', 'Unknown Source')}{Style.RESET_ALL}")
        if source_config.get("type") == "rss" and "url" in source_config:
            source_articles = fetch_articles_from_rss(source_config["url"], source_config["name"])
            all_articles.extend(source_articles)
        else:
            print(f"{Fore.YELLOW}Unsupported or misconfigured source: {source_config.get('name', 'Unknown Source')}{Style.RESET_ALL}")

    if not all_articles:
        print(f"{Fore.RED}No articles fetched from any source.{Style.RESET_ALL}")
        return []

    if stock_symbols:
        filtered_articles: List[Article] = []
        
        # Debug print to help troubleshoot
        print(f"{Fore.CYAN}Found {len(all_articles)} articles. Looking for mentions of {Fore.YELLOW}{', '.join(stock_symbols)}{Fore.CYAN}...{Style.RESET_ALL}")
        
        for article in all_articles:
            text_to_search = ((article.title or "") + " " + (article.summary or "")).lower() # Use lower for searching
            
            current_article_found_tickers = set()

            for original_symbol in stock_symbols:
                # Regex to find the ticker as a whole word, optionally preceded by $ or enclosed in ()
                # \b for word boundaries
                # re.IGNORECASE for case-insensitive matching
                # We need to escape parentheses if they are part of the pattern literal
                # The symbol itself should be escaped in case it contains regex special characters
                escaped_symbol = re.escape(original_symbol)
                
                # More flexible patterns to check:
                # 1. Whole word: \bSYMBOL\b
                # 2. Preceded by $: \$SYMBOL\b
                # 3. Enclosed in parentheses: \(SYMBOL\)
                # 4. More flexible company name matching for common stocks
                patterns = [
                    r'\b' + escaped_symbol + r'\b',              # Whole word
                    r'\$' + escaped_symbol + r'\b',              # $SYMBOL
                    r'\(' + escaped_symbol + r'\)',              # (SYMBOL)
                    r'ticker[s]?[\s:]+' + escaped_symbol,       # "ticker: SYMBOL" or "tickers: SYMBOL"
                    r'stock[s]?[\s:]+' + escaped_symbol,        # "stock: SYMBOL" or "stocks: SYMBOL"
                    r'shares? of ' + escaped_symbol,            # "shares of SYMBOL" or "share of SYMBOL"
                ]
                
                # Add company name patterns for well-known tickers
                company_name_patterns = {
                    'AAPL': [r'\bapple\b'],
                    'MSFT': [r'\bmicrosoft\b'],
                    'GOOG': [r'\bgoogle\b', r'\balphabet\b'],
                    'GOOGL': [r'\bgoogle\b', r'\balphabet\b'],
                    'AMZN': [r'\bamazon\b'],
                    'META': [r'\bmeta\b', r'\bfacebook\b'],
                    'TSLA': [r'\btesla\b', r'\bmusk\b'],
                    'NVDA': [r'\bnvidia\b'],
                }
                
                # Add company name patterns if we have them for this ticker
                if original_symbol in company_name_patterns:
                    patterns.extend(company_name_patterns[original_symbol])
                
                # Try each pattern
                for pattern in patterns:
                    if re.search(pattern, text_to_search, re.IGNORECASE):
                        current_article_found_tickers.add(original_symbol)
                        # Print when we find a match for debugging
                        print(f"{Fore.GREEN}Found ticker {Fore.YELLOW}{Style.BRIGHT}{original_symbol}{Style.RESET_ALL}{Fore.GREEN} in article: {Fore.WHITE}{article.title}{Style.RESET_ALL}")
                        break # Found this symbol, no need to check other patterns for it
            
            if current_article_found_tickers:
                article.tickers = sorted(list(current_article_found_tickers))
                # Fetch and store current prices for these tickers
                article.ticker_prices = fetch_current_prices(article.tickers)
                filtered_articles.append(article)
        return filtered_articles
    
    return all_articles
