import feedparser
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from article import Article
from datetime import datetime, timedelta
import time # For parsing dates
import yfinance as yf # Added yfinance
import re # For improved ticker matching
import pandas as pd # For processing stock lists
import os # For cache file management
# from colorama import init, Fore, Back, Style # Will use logging instead
import logging
import traceback # For logging exceptions
import concurrent.futures # For parallel processing
import functools # For caching

# Initialize colorama - replaced by logger
# init(autoreset=True)
logger = logging.getLogger(__name__) # Get logger instance

# Path to the sources configuration file
SOURCES_FILE = Path(__file__).parent / "sources.json"
# Path to the stock symbols cache file
STOCKS_CACHE_FILE = Path(__file__).parent / "stocks_cache.json"
# Path to the price cache file
PRICE_CACHE_FILE = Path(__file__).parent / "price_cache.json"
# Cache expiration in days
CACHE_EXPIRATION_DAYS = 7
# Price cache expiration in minutes
PRICE_CACHE_EXPIRATION_MINUTES = 30


def load_sources() -> List[Dict[str, Any]]:
    """Loads news sources from the JSON configuration file."""
    if not SOURCES_FILE.exists():
        logger.warning(f"Sources file not found at {SOURCES_FILE}")
        return []
    try:
        with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
            sources = json.load(f)
        logger.info(f"Successfully loaded {len(sources)} sources from {SOURCES_FILE}")
        return sources
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {SOURCES_FILE}: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Error loading sources file {SOURCES_FILE}: {e}", exc_info=True)
        return []


def fetch_articles_from_rss(feed_url: str, source_name: str) -> List[Article]:
    """Fetches and parses articles from an RSS feed."""
    articles: List[Article] = []
    logger.info(f"Fetching from RSS: {feed_url} (Source: {source_name})")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        logger.debug(f"Attempting to fetch feed from {feed_url} with agent {headers.get('User-Agent')}")
        feed_data = feedparser.parse(feed_url, agent=headers.get('User-Agent'))
        status = feed_data.status if hasattr(feed_data, 'status') else 'unknown'
        logger.debug(f"Feed fetched from {feed_url}. Status: {status}, Entries: {len(feed_data.entries)}")

        if feed_data.bozo:
            bozo_exception = feed_data.bozo_exception
            logger.warning(f"Ill-formed feed from {feed_url}. Reason: {bozo_exception}")

        for i, entry in enumerate(feed_data.entries):
            try:
                published_dt: Optional[datetime] = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    except TypeError:
                        logger.warning(f"Could not parse published_parsed for entry {i} from {source_name}", exc_info=True)
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    try:
                        published_dt = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                    except TypeError:
                        logger.warning(f"Could not parse updated_parsed for entry {i} from {source_name}", exc_info=True)

                summary = getattr(entry, 'summary', None) or getattr(entry, 'description', None)
                title = getattr(entry, 'title', 'N/A')
                
                logger.debug(f"Processing entry {i} from {source_name}: {title[:40]}...")
                
                article = Article(
                    title=title,
                    link=getattr(entry, 'link', 'N/A'),
                    published_date=published_dt,
                    summary=summary,
                    source=source_name
                )
                articles.append(article)
            except Exception as entry_ex:
                logger.error(f"Error processing entry {i} from {source_name} ('{title[:40]}...'): {entry_ex}", exc_info=True)
        
        logger.info(f"Successfully processed {len(articles)} articles from {source_name}")
    except Exception as e:
        logger.error(f"Error fetching or parsing RSS feed from {feed_url}: {repr(e)}", exc_info=True)
        # traceback.print_exc() # Already handled by exc_info=True
    return articles


# Load and manage price cache
def load_price_cache() -> Dict[str, Dict]:
    """Load cached stock prices from file"""
    if not PRICE_CACHE_FILE.exists():
        return {}
    
    try:
        with open(PRICE_CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            return cache
    except Exception as e:
        logger.warning(f"Error reading price cache: {e}", exc_info=True)
        return {}


def save_price_cache(cache: Dict[str, Dict]) -> None:
    """Save price cache to file"""
    try:
        with open(PRICE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving price cache: {e}", exc_info=True)


def get_cached_price(ticker: str, cache: Dict[str, Dict]) -> Optional[float]:
    """Get price from cache if valid"""
    if ticker not in cache:
        return None
    
    cache_time = cache[ticker].get('timestamp')
    if not cache_time:
        return None
    
    # Check if cache is still valid (within PRICE_CACHE_EXPIRATION_MINUTES)
    cache_dt = datetime.fromtimestamp(cache_time)
    if datetime.now() - cache_dt > timedelta(minutes=PRICE_CACHE_EXPIRATION_MINUTES):
        return None
        
    return cache[ticker].get('price')


def fetch_single_ticker_price(ticker: str, price_cache: Dict[str, Dict]) -> Optional[float]:
    """Fetch price for a single ticker, with caching"""
    # Check cache first
    cached_price = get_cached_price(ticker, price_cache)
    if cached_price is not None:
        logger.debug(f"Using cached price for {ticker}: {cached_price}")
        return cached_price
    
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        current_price = info.get('currentPrice') or \
                        info.get('regularMarketPrice') or \
                        info.get('previousClose')

        if current_price is None:
            logger.debug(f"Current price not in info for {ticker}, trying history.")
            hist = ticker_obj.history(period="2d")
            if not hist.empty and 'Close' in hist.columns:
                current_price = hist['Close'].iloc[-1]
        
        if current_price is not None:
            price = float(current_price)
            # Update cache
            price_cache[ticker] = {
                'price': price,
                'timestamp': datetime.now().timestamp()
            }
            logger.debug(f"Fetched price for {ticker}: {price}")
            return price
        else:
            logger.warning(f"Could not fetch price for {ticker} after multiple attempts.")
            return None
    except Exception as e:
        logger.error(f"Error fetching price for {ticker} with yfinance: {e}", exc_info=True)
        return None


def fetch_current_prices(ticker_symbols: List[str]) -> Dict[str, float]:
    """Fetches current prices for a list of stock tickers using yfinance, with parallel requests and caching."""
    prices: Dict[str, float] = {}
    if not ticker_symbols:
        return prices
    
    logger.debug(f"Fetching current prices for tickers: {ticker_symbols}")
    
    # Load price cache
    price_cache = load_price_cache()
    
    # Use ThreadPoolExecutor for parallel fetching
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # Create a partial function with the price_cache parameter
        fetch_with_cache = functools.partial(fetch_single_ticker_price, price_cache=price_cache)
        
        # Map tickers to their fetched prices in parallel
        future_to_ticker = {executor.submit(fetch_with_cache, ticker): ticker for ticker in ticker_symbols}
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                price = future.result()
                if price is not None:
                    prices[ticker] = price
            except Exception as e:
                logger.error(f"Exception when fetching price for {ticker}: {e}", exc_info=True)
    
    # Save updated cache
    save_price_cache(price_cache)
    
    return prices


def generate_mock_articles() -> List[Article]:
    """Generates mock articles for testing purposes."""
    logger.info("Generating mock articles for testing...")
    
    mock_articles_data = [
        {
            "title": "Mock Apple Reports Record Earnings in Q3", "source": "Mock Finance News",
            "summary": "Apple Inc. (AAPL) mock reported record earnings...", "tickers": ["AAPL"], "hours_ago": 2
        },
        {
            "title": "Mock Tesla Announces New Factory in Europe", "source": "Mock Tech News",
            "summary": "Tesla (TSLA) mock announced plans for a new Gigafactory...", "tickers": ["TSLA"], "hours_ago": 4
        },
        {
            "title": "Mock AAPL & TSLA Strong Market Performance", "source": "Mock Market Watch",
            "summary": "Both Apple (AAPL) and Tesla (TSLA) mock shares have shown...", "tickers": ["AAPL", "TSLA"], "hours_ago": 1
        },
        {
            "title": "Mock Tech Sector Leads Gains (AAPL)", "source": "Mock Market Analysis",
            "summary": "The mock tech sector is leading market gains today, with Apple (AAPL)...", "tickers": ["AAPL"], "hours_ago": 6
        },
        {
            "title": "Mock Tesla Unveils New Battery Tech", "source": "Mock EV News",
            "summary": "Tesla (TSLA) mock unveiled a new battery technology...", "tickers": ["TSLA"], "hours_ago": 12
        }
    ]
    
    articles = []
    now = datetime.now()
    for data in mock_articles_data:
        published_date = now - timedelta(hours=data["hours_ago"])
        article = Article(
            title=data["title"],
            link=f"https://example.com/mock-article-{abs(hash(data['title'])) % 10000}", # abs for hash
            published_date=published_date,
            summary=data["summary"],
            source=data["source"],
            tickers=data["tickers"]
        )
        if data["tickers"]:
            article.ticker_prices = {t: (150.00 + i*10) for i, t in enumerate(data["tickers"])} # Simple mock prices
        articles.append(article)
    
    logger.info(f"Generated {len(articles)} mock articles.")
    return articles


def fetch_major_stocks() -> Dict[str, str]:
    """
    Fetches NASDAQ and S&P 500 stocks and maps tickers to company names.
    Uses a local cache file to avoid repeated API calls.
    
    Returns:
        Dict mapping ticker symbols to company names
    """
    # Check if we have a valid cache file
    if STOCKS_CACHE_FILE.exists():
        try:
            cache_stat = os.stat(STOCKS_CACHE_FILE)
            cache_age = datetime.now() - datetime.fromtimestamp(cache_stat.st_mtime)
            if cache_age.days < CACHE_EXPIRATION_DAYS:
                logger.info(f"Using cached stock symbols (age: {cache_age.days} days)")
                with open(STOCKS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Error reading cache file: {e}", exc_info=True)
    
    logger.info("Fetching major stock indices (NASDAQ and S&P 500)")
    stock_map = {}
    
    try:
        # Fetch S&P 500 components
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        for idx, row in sp500.iterrows():
            ticker = row['Symbol']
            company = row['Security']
            stock_map[ticker] = company
        logger.info(f"Fetched {len(sp500)} S&P 500 companies")
        
        # Fetch NASDAQ components (this may contain duplicates with S&P 500)
        try:
            nasdaq_tables = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
            # Find the right table - inspect column names
            for table_idx, table in enumerate(nasdaq_tables):
                logger.debug(f"NASDAQ table {table_idx} columns: {list(table.columns)}")
                
                # Try different commonly used column names for tickers
                ticker_col = None
                company_col = None
                
                possible_ticker_cols = ['Ticker', 'Symbol', 'Ticker symbol', 'Trading symbol']
                possible_company_cols = ['Company', 'Security', 'Name', 'Company name']
                
                for col in table.columns:
                    if col in possible_ticker_cols:
                        ticker_col = col
                    elif col in possible_company_cols:
                        company_col = col
                
                # If we found both columns, use this table
                if ticker_col and company_col:
                    logger.info(f"Using NASDAQ table {table_idx} with columns {ticker_col} and {company_col}")
                    for idx, row in table.iterrows():
                        ticker = row[ticker_col]
                        company = row[company_col]
                        stock_map[ticker] = company
                    break
            
            logger.info(f"Total unique tickers after adding NASDAQ: {len(stock_map)}")
        except Exception as nasdaq_error:
            logger.error(f"Error processing NASDAQ table: {nasdaq_error}", exc_info=True)
        
        # Cache the results
        with open(STOCKS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(stock_map, f, indent=2)
        logger.info(f"Cached stock symbols to {STOCKS_CACHE_FILE}")
        
    except Exception as e:
        logger.error(f"Error fetching stock lists: {e}", exc_info=True)
        # If fetch fails but we have an existing cache, use it even if expired
        if STOCKS_CACHE_FILE.exists():
            logger.warning("Using expired cache due to fetch error")
            try:
                with open(STOCKS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as cache_e:
                logger.error(f"Error reading cache file: {cache_e}", exc_info=True)
        
        # If all else fails, return a minimal set of well-known stocks
        logger.warning("Returning minimal fallback stock list")
        stock_map = {
            'AAPL': 'Apple Inc.',
            'MSFT': 'Microsoft Corporation',
            'GOOG': 'Alphabet Inc. (Google) Class C',
            'GOOGL': 'Alphabet Inc. (Google) Class A',
            'AMZN': 'Amazon.com, Inc.',
            'META': 'Meta Platforms, Inc.',
            'TSLA': 'Tesla, Inc.',
            'NVDA': 'NVIDIA Corporation',
            'JPM': 'JPMorgan Chase & Co.',
            'V': 'Visa Inc.',
            'WMT': 'Walmart Inc.',
            'JNJ': 'Johnson & Johnson',
            'PG': 'Procter & Gamble Co.',
            'XOM': 'Exxon Mobil Corporation',
            'BAC': 'Bank of America Corp.',
        }
    
    return stock_map


# Precompile commonly used regex patterns for better performance
TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b')
PARENS_TICKER_PATTERN = re.compile(r'\(([A-Z]{1,5})\)')

# Define common word tickers that need special handling
COMMON_WORD_TICKERS = {
    'SHOP': True, 'NOW': True, 'SNAP': True, 'GO': True, 'A': True, 
    'FOR': True, 'ALL': True, 'ARE': True, 'REAL': True, 'ON': True, 
    'IT': True, 'BE': True, 'FAST': True, 'PLAY': True, 'SEE': True, 
    'BILL': True, 'BIG': True, 'GOOD': True, 'LOW': True, 'WELL': True,
}


def fetch_articles_in_parallel(sources: List[Dict[str, Any]]) -> List[Article]:
    """Fetch articles from multiple sources in parallel"""
    all_articles = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_source = {}
        
        for source_config in sources:
            name = source_config.get('name', 'Unknown Source')
            if source_config.get("type") == "rss" and "url" in source_config:
                future = executor.submit(fetch_articles_from_rss, source_config["url"], name)
                future_to_source[future] = name
        
        for future in concurrent.futures.as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                source_articles = future.result()
                all_articles.extend(source_articles)
                logger.info(f"Added {len(source_articles)} articles from {source_name}")
            except Exception as e:
                logger.error(f"Error getting articles from {source_name}: {e}", exc_info=True)
    
    return all_articles


def fetch_all_news(stock_symbols: Optional[List[str]] = None, source_limit: Optional[int] = None, use_mock: bool = False) -> List[Article]:
    """
    Fetches news from all configured sources or generates mock articles.
    Filters by stock symbols if provided.
    """
    if use_mock:
        logger.info("Using mock articles as requested.")
        articles_to_return = generate_mock_articles()
        if stock_symbols:
            logger.debug(f"Filtering {len(articles_to_return)} mock articles for symbols: {stock_symbols}")
            articles_to_return = [article for article in articles_to_return if article.tickers and any(s in article.tickers for s in stock_symbols)]
            logger.debug(f"{len(articles_to_return)} mock articles remained after filtering by symbols.")
        return articles_to_return
    
    logger.info("Fetching real news articles.")
    all_articles: List[Article] = []
    sources = load_sources()

    if source_limit is not None:
        if source_limit > 0:
            sources = sources[:source_limit]
            logger.info(f"Limiting to first {len(sources)} source(s) as per source_limit={source_limit}.")
        else:
            logger.warning(f"--source-limit is non-positive ({source_limit}), processing all sources.")

    # Fetch articles from sources in parallel
    all_articles = fetch_articles_in_parallel(sources)

    if not all_articles:
        logger.warning("No articles fetched from any real source.")
        return []
    logger.info(f"Fetched {len(all_articles)} articles from all real sources before stock symbol filtering.")

    # Get stock ticker to company name mapping
    stock_map = fetch_major_stocks()
    
    # Define symbols to scan based on input
    if stock_symbols:
        symbols_to_scan = stock_symbols
        # Expand company-based queries to ticker symbols if needed
        expanded_symbols = []
        for symbol in stock_symbols:
            # If it looks like a company name, not a ticker, try to find matching tickers
            if len(symbol) > 5 and not symbol.isupper():
                symbol_lower = symbol.lower()
                for ticker, company in stock_map.items():
                    if symbol_lower in company.lower():
                        expanded_symbols.append(ticker)
                        logger.info(f"Expanded company name '{symbol}' to ticker '{ticker}'")
            else:
                expanded_symbols.append(symbol)
        
        if expanded_symbols and expanded_symbols != stock_symbols:
            logger.info(f"Expanded search from {stock_symbols} to {expanded_symbols}")
            symbols_to_scan = expanded_symbols
    else:
        # If no specific symbols requested, use common ones
        symbols_to_scan = list(stock_map.keys())
        # Limit to most common stocks if we have a large list to avoid performance issues
        if len(symbols_to_scan) > 20:
            common_stock_symbols = ['AAPL', 'MSFT', 'GOOG', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA']
            symbols_to_scan = [s for s in common_stock_symbols if s in stock_map] + symbols_to_scan[:20]
    
    logger.info(f"Analyzing {len(all_articles)} articles for stock symbols: {symbols_to_scan[:10]}... (total: {len(symbols_to_scan)})")
    processed_articles: List[Article] = []
    
    # Create patterns for company names based on stock map
    company_patterns = {}
    for ticker, company in stock_map.items():
        if ticker in symbols_to_scan:
            # Create patterns for this company name
            name_parts = company.split()
            main_name = name_parts[0].lower()  # First word usually has the company name
            
            # Handle special cases and common nicknames
            if ticker == 'AAPL' or 'Apple' in company:
                patterns = [r'\bapple\b']
            elif ticker == 'MSFT' or 'Microsoft' in company:
                patterns = [r'\bmicrosoft\b']
            elif ticker == 'GOOG' or ticker == 'GOOGL' or 'Google' in company or 'Alphabet' in company:
                patterns = [r'\bgoogle\b', r'\balphabet\b']
            elif ticker == 'AMZN' or 'Amazon' in company:
                patterns = [r'\bamazon\b']
            elif ticker == 'META' or 'Meta' in company or 'Facebook' in company:
                patterns = [r'\bmeta\b', r'\bfacebook\b']
            elif ticker == 'TSLA' or 'Tesla' in company:
                patterns = [r'\btesla\b', r'\bmusk\b']  # Elon Musk is often mentioned with Tesla
            elif ticker == 'NVDA' or 'NVIDIA' in company:
                patterns = [r'\bnvidia\b']
            else:
                # For other companies, use the company name
                # Escape any regex special characters in the company name
                escaped_name = re.escape(main_name)
                patterns = [r'\b' + escaped_name + r'\b']
                
                # If company name has multiple parts, add the full name too
                if len(name_parts) > 1:
                    full_name = re.escape(company.lower())
                    patterns.append(r'\b' + full_name + r'\b')
            
            company_patterns[ticker] = patterns
    
    # First pass: fast scan using optimized regex for ticker symbols
    for article in all_articles:
        title_text = article.title.lower() if article.title else ""
        summary_text = article.summary.lower() if article.summary else ""
        full_text = title_text + " " + summary_text
        
        # Track ticker occurrences with a score to prioritize those most likely to be the main subject
        ticker_scores = {}
        primary_ticker = None
        highest_score = 0
        
        # Use precompiled regex to find ticker symbols in $ format and parentheses
        dollar_tickers = TICKER_PATTERN.findall(full_text.upper())
        parens_tickers = PARENS_TICKER_PATTERN.findall(full_text.upper())
        
        # Add initial scores for explicitly marked tickers
        for ticker in dollar_tickers + parens_tickers:
            if ticker in symbols_to_scan:
                ticker_scores[ticker] = ticker_scores.get(ticker, 0) + 8
        
        # Now check for the actual ticker matches and company names
        for ticker in symbols_to_scan:
            # Skip very short tickers that are likely to cause false positives
            if len(ticker) == 1:
                continue
                
            # Skip if we already found it via regex
            if ticker in ticker_scores:
                continue
            
            # Initialize score for this ticker if not set
            if ticker not in ticker_scores:
                ticker_scores[ticker] = 0
                
            ticker_found = False
            
            # Check for ticker in title (high importance)
            if ticker in COMMON_WORD_TICKERS:
                # For common words, use stricter patterns
                title_patterns = [
                    r'\$' + re.escape(ticker) + r'\b',
                    r'\(' + re.escape(ticker) + r'\)',
                    # Exact match case-sensitive for ticker
                    re.escape(ticker)
                ]
                
                # Check title for exact ticker match first (case sensitive)
                if re.search(re.escape(ticker) + r'(?=[^a-zA-Z0-9]|$)', article.title or "", re.DOTALL):
                    ticker_scores[ticker] += 10  # High score for exact ticker match in title
                    ticker_found = True
            else:
                # Standard ticker patterns
                title_presence = ticker.lower() in title_text or \
                                f"${ticker.lower()}" in title_text or \
                                f"({ticker.lower()})" in title_text
                
                if title_presence:
                    ticker_scores[ticker] += 8  # High score for ticker in title
                    ticker_found = True
            
            # Check for company name in title (very high importance)
            if ticker in company_patterns:
                for pattern in company_patterns[ticker]:
                    if re.search(pattern, title_text, re.IGNORECASE):
                        ticker_scores[ticker] += 12  # Very high score for company name in title
                        ticker_found = True
                        break
            
            # For common word tickers, verify financial context
            if ticker in COMMON_WORD_TICKERS and ticker_found:
                financial_context_words = ["stock", "share", "price", "market", "investor", "trading", 
                                          "nasdaq", "nyse", "exchange", "financ", "earn", "revenue"]
                
                # Check if financial context exists
                if not any(word in full_text for word in financial_context_words):
                    # Likely not actually about the stock, reset score
                    ticker_scores[ticker] = 0
                    ticker_found = False
            
            # Only check summary if not already found in title or for additional scoring
            if not ticker_found or ticker_scores[ticker] < 8:
                # For common word tickers, use more restrictive patterns for summary
                if ticker in COMMON_WORD_TICKERS:
                    # Only match exact ticker references with $ prefix or in specific financial contexts
                    summary_patterns = [
                        r'\$' + re.escape(ticker) + r'\b',
                        r'\(' + re.escape(ticker) + r'\)',
                        r'ticker[s]?[\s:]+' + re.escape(ticker) + r'\b',
                        r'stock[s]?[\s:]+' + re.escape(ticker) + r'\b',
                        r'symbol[\s:]+' + re.escape(ticker) + r'\b',
                        r'shares? of ' + re.escape(ticker) + r'\b',
                    ]
                    
                    for pattern in summary_patterns:
                        if re.search(pattern, summary_text, re.IGNORECASE):
                            ticker_scores[ticker] += 5  # Medium score for ticker in summary
                            ticker_found = True
                            break
                            
                    # Case sensitive check for exact ticker match in summary
                    if not ticker_found and re.search(re.escape(ticker) + r'(?=[^a-zA-Z0-9]|$)', article.summary or "", re.DOTALL):
                        ticker_scores[ticker] += 3  # Lower score for exact ticker match in summary
                        ticker_found = True
                else:
                    # Standard ticker check in summary
                    summary_presence = ticker.lower() in summary_text or \
                                      f"${ticker.lower()}" in summary_text or \
                                      f"({ticker.lower()})" in summary_text
                    
                    if summary_presence:
                        ticker_scores[ticker] += 4  # Medium score for ticker in summary
                        ticker_found = True
                
                # Check for company name in summary if ticker not found yet
                if not ticker_found and ticker in company_patterns:
                    for pattern in company_patterns[ticker]:
                        if re.search(pattern, summary_text, re.IGNORECASE):
                            # Check frequency of mentions
                            matches = re.findall(pattern, summary_text, re.IGNORECASE)
                            ticker_scores[ticker] += 2 + min(len(matches), 3)  # Base score + bonus for frequency
                            ticker_found = True
                            break
            
            # Update primary ticker if this has the highest score
            if ticker_scores[ticker] > highest_score:
                highest_score = ticker_scores[ticker]
                primary_ticker = ticker
        
        # Second pass: determine which tickers to include in the article
        current_article_found_tickers = set()
        
        # Only include tickers with a minimum threshold score
        for ticker, score in ticker_scores.items():
            if score >= 3:  # Minimum threshold for inclusion
                current_article_found_tickers.add(ticker)
                # Log the score for debugging
                logger.debug(f"Ticker {ticker} for article '{article.title[:40]}...' has score {score}")
        
        # Always include primary ticker if it exists and has a non-zero score
        if primary_ticker and ticker_scores[primary_ticker] > 0:
            current_article_found_tickers.add(primary_ticker)
            # Mark the primary ticker in the article for future reference
            article.primary_ticker = primary_ticker
            logger.debug(f"Primary ticker for article '{article.title[:40]}...' is {primary_ticker} with score {ticker_scores[primary_ticker]}")
        
        # Set the tickers for this article
        if current_article_found_tickers:
            article.tickers = sorted(list(current_article_found_tickers))
            if article.tickers:  # Ensure tickers are present before fetching prices
                article.ticker_prices = fetch_current_prices(article.tickers)
        
        # Only filter out articles if specific stock symbols were requested
        if stock_symbols:
            if current_article_found_tickers and any(s in current_article_found_tickers for s in symbols_to_scan):
                # For stricter filtering, only include if one of the requested symbols is the primary ticker
                # or has a high enough score
                should_include = False
                
                for s in symbols_to_scan:
                    if s in current_article_found_tickers:
                        # Include if it's the primary ticker or has a high score
                        if s == primary_ticker or ticker_scores.get(s, 0) >= 8:
                            should_include = True
                            break
                
                if should_include:
                    processed_articles.append(article)
            
        else:
            # If no specific symbols requested, keep all articles with identified tickers
            processed_articles.append(article)
    
    if stock_symbols:
        logger.info(f"{len(processed_articles)} articles remained after filtering for symbols: {symbols_to_scan}")
    else:
        logger.info(f"Returning {len(processed_articles)} articles with analyzed tickers.")
    
    return processed_articles
