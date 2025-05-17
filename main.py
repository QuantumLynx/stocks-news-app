import argparse
from datetime import datetime, timedelta # Added timedelta 
from news_fetcher import fetch_all_news
from article import Article # For type hinting
from typing import List, Optional # Added Optional
from colorama import init, Fore, Back, Style

# Initialize colorama
init(autoreset=True)

def display_articles(articles: List[Article]):
    """Displays articles to the console with colorful formatting."""
    if not articles:
        print(f"{Fore.YELLOW}No news articles found matching your criteria.{Style.RESET_ALL}")
        return

    print(f"\n{Fore.GREEN}Found {len(articles)} articles:{Style.RESET_ALL}\n")
    for i, article in enumerate(articles, 1):
        # Article header
        print(f"{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}{'=' * 70}{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE}{Style.BRIGHT} ARTICLE {i} {' ' * (70 - 10 - len(str(i)))}{Style.RESET_ALL}")
        print(f"{Back.BLUE}{Fore.WHITE}{Style.BRIGHT}{'=' * 70}{Style.RESET_ALL}")
        
        # Article details
        print(f"{Fore.CYAN}Title:    {Fore.WHITE}{Style.BRIGHT}{article.title}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Source:   {Fore.WHITE}{article.source}{Style.RESET_ALL}")
        if article.published_date:
            print(f"{Fore.CYAN}Date:     {Fore.WHITE}{article.published_date.strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Link:     {Fore.BLUE}{Style.BRIGHT}{article.link}{Style.RESET_ALL}")
        
        if article.summary:
            # Basic HTML tag removal for cleaner summary preview
            summary_text = article.summary
            import re
            summary_text = re.sub('<[^<]+?>', '', summary_text) # Remove HTML tags
            summary_preview = summary_text.replace('\n', ' ').strip()
            # Simple word wrapping for summary
            print(f"\n{Fore.CYAN}Summary:{Style.RESET_ALL}")
            max_line_length = 68 # Roughly 70 - "Summary: ".length
            current_line = ""
            for word in summary_preview.split():
                if len(current_line) + len(word) + 1 > max_line_length:
                    print(f"  {Fore.WHITE}{current_line}{Style.RESET_ALL}")
                    current_line = word
                else:
                    current_line += (" " + word) if current_line else word
            if current_line: # Print any remaining part of the summary
                print(f"  {Fore.WHITE}{current_line}{Style.RESET_ALL}")
            
        if article.tickers:
            print(f"\n{Fore.CYAN}Tickers:  {Fore.YELLOW}{Style.BRIGHT}{', '.join(article.tickers)}{Style.RESET_ALL}")
            if article.ticker_prices:
                price_details = [
                    f"{ticker}: {Fore.GREEN}${price:.2f}{Style.RESET_ALL}" for ticker, price in article.ticker_prices.items() if price is not None
                ]
                if price_details:
                    print(f"{Fore.CYAN}Prices:   {' '.join(price_details)}")
        print(f"{Fore.BLUE}{Style.BRIGHT}{'=' * 70}{Style.RESET_ALL}")
        print() # Add a blank line between articles


def main():
    """Main function to parse arguments and fetch/display news."""
    parser = argparse.ArgumentParser(
        description="Finance Stock News Collector. Fetches news from RSS feeds and filters by stock symbols."
    )
    parser.add_argument(
        "--stocks",
        type=str,
        help="Comma-separated list of stock symbols to filter news for (e.g., AAPL,MSFT,GOOG). Leave empty for general news."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of articles to display (default: 10)."
    )
    parser.add_argument(
        "--source-limit",
        type=int,
        help="Maximum number of feed sources to process from sources.json."
    )
    parser.add_argument(
        "--time-interval",
        type=str,
        choices=["today", "last-hour", "last-4-hours", "last-12-hours", "last-24-hours", "last-15-minutes", "last-30-minutes"],
        help="Filter articles by publication time (e.g., today, last-hour, last-4-hours, last-15-minutes)."
    )

    args = parser.parse_args()

    # Print welcome message
    print(f"\n{Back.WHITE}{Fore.BLACK}{Style.BRIGHT} Finance Stock News Collector {Style.RESET_ALL}")
    
    stock_symbols_list: Optional[List[str]] = None
    if args.stocks:
        stock_symbols_list = [symbol.strip().upper() for symbol in args.stocks.split(',') if symbol.strip()]
        if stock_symbols_list:
            print(f"{Fore.CYAN}Fetching news for stocks: {Fore.YELLOW}{Style.BRIGHT}{', '.join(stock_symbols_list)}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}No valid stock symbols provided, fetching general news.{Style.RESET_ALL}")
            stock_symbols_list = None # Treat empty or whitespace-only as general news
    else:
        print(f"{Fore.CYAN}Fetching general finance news (no stock symbols specified)...{Style.RESET_ALL}")

    articles = fetch_all_news(stock_symbols=stock_symbols_list, source_limit=args.source_limit)
    
    # Sort articles by published date, newest first (if available)
    articles.sort(key=lambda x: x.published_date if x.published_date else datetime.min, reverse=True)
    
    # Apply time interval filtering if specified
    if args.time_interval and articles:
        now = datetime.now()
        time_filter = None
        
        if args.time_interval == "today":
            time_filter = datetime(now.year, now.month, now.day, 0, 0, 0)
        elif args.time_interval == "last-hour":
            time_filter = now - timedelta(hours=1)
        elif args.time_interval == "last-4-hours":
            time_filter = now - timedelta(hours=4)
        elif args.time_interval == "last-12-hours":
            time_filter = now - timedelta(hours=12)
        elif args.time_interval == "last-24-hours":
            time_filter = now - timedelta(hours=24)
        elif args.time_interval == "last-15-minutes":
            time_filter = now - timedelta(minutes=15)
        elif args.time_interval == "last-30-minutes":
            time_filter = now - timedelta(minutes=30)
            
        if time_filter:
            print(f"{Fore.MAGENTA}Filtering articles published since: {Fore.WHITE}{time_filter}{Style.RESET_ALL}")
            filtered_articles = [article for article in articles if article.published_date and article.published_date >= time_filter]
            articles = filtered_articles
    
    display_articles(articles[:args.limit])


if __name__ == "__main__":
    main()
