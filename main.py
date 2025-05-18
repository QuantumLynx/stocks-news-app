import argparse
from datetime import datetime, timedelta
from news_fetcher import fetch_all_news, fetch_major_stocks
from article import Article  # For type hinting
from typing import List, Optional
import re # For HTML stripping in summary
import logging # Added logging

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, ListView, ListItem, Label, Button
from textual.reactive import reactive
from textual.binding import Binding
from textual.screen import ModalScreen
from textual import events

# For initial messages before TUI starts - will be replaced by logging
# from colorama import init, Fore, Back, Style
# init(autoreset=True)

# Configure logging
LOG_FILE = "app.log"
logging.basicConfig(
    level=logging.INFO, # Default level is INFO for cleaner output
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'), # Overwrite log file each run
        logging.StreamHandler() # Also print to console for immediate feedback
    ]
)
logger = logging.getLogger(__name__)


class ArticleDetailPane(Static):
    """A widget to display the details of a selected article."""
    selected_article = reactive(None)
    parent_app = None  # Reference to the parent NewsTUI object for accessing articles

    def _format_article_details(self, article: Optional[Article]) -> str:
        if not article:
            return "[bold yellow]No article selected. Select an article from the list on the left.[/]"

        details = []
        
        # Use highly visible formatting for content
        details.append(f"[bold white on blue] ARTICLE DETAILS [/]")
        details.append("")
        
        details.append(f"[bold white]TITLE:[/] {article.title}")
        details.append("")
        
        details.append(f"[bold green]SOURCE:[/] {article.source}")
        
        if article.published_date:
            details.append(f"[bold cyan]DATE:[/] {article.published_date.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            details.append(f"[bold cyan]DATE:[/] N/A")
            
        details.append(f"[bright_blue underline]LINK:[/] {article.link}")
        details.append("")

        if article.tickers:
            # Use regular string without rich text formatting for tickers to avoid markup issues
            ticker_text = ', '.join(article.tickers)
            details.append(f"[bold yellow]TICKERS:[/] {ticker_text}")
            
            if article.ticker_prices:
                price_details_list = []
                for ticker, price in article.ticker_prices.items():
                    if price is not None:
                        # Ensure we properly escape any rich text formatting within ticker symbols
                        safe_ticker = ticker.replace('[', '\\[').replace(']', '\\]')
                        price_details_list.append(f"{safe_ticker}: [green]${price:.2f}[/]")
                
                if price_details_list:
                    prices_text = ' '.join(price_details_list)
                    details.append(f"[bold magenta]PRICES:[/] {prices_text}")
            
            details.append("")

        # Summary section with basic formatting
        details.append("[bold white]SUMMARY:[/]")
        if article.summary:
            summary_text = article.summary
            # Simple cleanup of HTML
            summary_text = re.sub('<[^<]+?>', ' ', summary_text)
            summary_text = re.sub(r'\s+', ' ', summary_text).strip()
            # Escape any potential rich text formatting characters in the content
            summary_text = summary_text.replace('[', '\\[').replace(']', '\\]')
            details.append(f"{summary_text}")
        else:
            details.append("[italic]No summary available[/]")
        
        # Add related articles section
        if article.tickers and self.parent_app and hasattr(self.parent_app, 'all_articles') and len(self.parent_app.all_articles) > 1:
            details.append("")
            details.append("[bold white on blue] RELATED ARTICLES [/]")
            
            # Find articles with related tickers
            related_articles = []
            current_tickers = set(article.tickers)
            
            for other_article in self.parent_app.all_articles:
                # Skip the current article
                if other_article is article:
                    continue
                    
                # Check if this article has any of the same tickers
                if other_article.tickers and current_tickers.intersection(set(other_article.tickers)):
                    related_articles.append(other_article)
            
            if related_articles:
                details.append("")
                # Show up to 3 related articles
                for i, related in enumerate(related_articles[:3]):
                    date_str = related.published_date.strftime('%m-%d %H:%M') if related.published_date else "No Date"
                    title_str = related.title[:45] + "..." if len(related.title) > 45 else related.title
                    tickers_str = ", ".join(related.tickers) if related.tickers else ""
                    details.append(f"[cyan]{date_str}[/] [bold white]{title_str}[/] [yellow]({tickers_str})[/]")
            else:
                details.append("[italic]No related articles found[/]")
        
        details.append("")
        details.append("[dim]Press Up/Down arrows to navigate, 'f' to filter, 'r' to reset, 'q' to quit.[/]")
        
        return "\n".join(details)

    def watch_selected_article(self, article: Optional[Article]) -> None:
        """Called when the selected_article reactive attribute changes."""
        try:
            formatted_content = self._format_article_details(article)
            self.update(formatted_content)
        except Exception as e:
            logger.error(f"Error displaying article: {str(e)}", exc_info=True)
            self.update(f"[bold red]Error displaying article: {str(e)}[/]")


class NewsTUI(App):
    """A Textual TUI for browsing financial news articles."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("up", "cursor_up", "Cursor Up", show=False),
        Binding("down", "cursor_down", "Cursor Down", show=False),
        Binding("f", "show_filter_menu", "Filter by ticker"),
        Binding("r", "reset_filter", "Reset filter"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }
    #main_container {
        layout: horizontal;
        height: 1fr; /* Fill available space */
    }
    #list_view_container {
        width: 40%; /* Make it wider for better visibility */
        height: 100%;
        border-right: solid $primary;
    }
    #article_list_view {
        height: 100%;
        border: none; /* Remove default border if any */
    }
    #detail_view_container {
        width: 1fr; /* Fill remaining width */
        height: 100%;
        padding: 0 2; /* More padding for better readability */
    }
    ArticleDetailPane {
        width: 100%;
        height: 100%;
        overflow-y: auto;
        background: $surface;
        color: $text;
    }
    Footer {
        height: auto;
        dock: bottom;
    }
    Header {
        dock: top;
    }
    .article-list-item {
        padding: 1 1;
        border-bottom: solid $primary-darken-1;
    }
    .article-list-item:hover {
        background: $accent-darken-2;
    }
    Label {
        width: 100%;
    }
    
    /* Ticker filter dialog styling */
    #ticker_dialog {
        background: $surface;
        border: solid $primary;
        padding: 1;
        width: 50%;
        height: auto;
        margin: 2 4 2 4;
        align: center middle;
    }
    
    #ticker_dialog_title {
        text-align: center;
        background: $primary;
        color: $text;
        padding: 1;
        margin-bottom: 1;
    }
    
    #ticker_dialog Button {
        margin: 1 0;
        width: 100%;
    }
    
    #ticker_dialog Button.selected {
        background: $accent;
        color: $text;
        border: solid $accent-lighten-2;
    }
    
    #ticker_dialog Button:focus {
        background: $accent;
        color: $text;
    }
    
    #cancel-button {
        margin-top: 2;
        background: $error;
    }
    """

    def __init__(self, articles: List[Article], cli_args: argparse.Namespace):
        super().__init__()
        self.articles: List[Article] = articles
        # Make sure we create a proper copy of the articles for filtering
        self.all_articles: List[Article] = articles.copy()  # Store original list for filtering
        self.cli_args: argparse.Namespace = cli_args
        self.article_list_pane: Optional[ListView] = None
        self.article_detail_pane: Optional[ArticleDetailPane] = None
        self.current_filter: Optional[str] = None
        self.loaded_successfully = False
        
        # Debug initialization
        logger.debug(f"NewsTUI initialized with {len(articles)} articles")
        logger.debug(f"self.articles has {len(self.articles)} items and self.all_articles has {len(self.all_articles)} items")

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header(name="Finance Stock News Collector")
        with Horizontal(id="main_container"):
            with Vertical(id="list_view_container"):
                self.article_list_pane = ListView(id="article_list_view")
                yield self.article_list_pane
            with Vertical(id="detail_view_container"):
                self.article_detail_pane = ArticleDetailPane(id="article_detail_content")
                self.article_detail_pane.parent_app = self  # Set parent reference for accessing articles
                yield self.article_detail_pane
        yield Footer()

    async def on_mount(self) -> None:
        """Called when the app is mounted."""
        logger.debug(f"NewsTUI.on_mount() starting. Initial self.article_list_pane type: {type(self.article_list_pane)}, Initial self.article_detail_pane type: {type(self.article_detail_pane)}")
        current_article_list_pane = None # Local var for clarity
        current_article_detail_pane = None

        try:
            try:
                current_article_list_pane = self.query_one("#article_list_view", ListView)
                current_article_detail_pane = self.query_one("#article_detail_content", ArticleDetailPane)
                # Assign to self as well, as other methods might use them
                self.article_list_pane = current_article_list_pane
                self.article_detail_pane = current_article_detail_pane
                
                # Set the parent_app reference on the detail pane
                if self.article_detail_pane:
                    self.article_detail_pane.parent_app = self
                
                logger.debug(f"NewsTUI.on_mount() after query_one: current_article_list_pane is {type(current_article_list_pane)}, current_article_detail_pane is {type(current_article_detail_pane)}")
            except Exception as e_query: 
                logger.critical(f"CRITICAL: Could not query #article_list_view or #article_detail_content in on_mount: {e_query}", exc_info=True)
                self.notify("Critical TUI error: UI panes not found. Check log.", severity="error")
                placeholder_detail_pane = self.query(ArticleDetailPane).first()
                if placeholder_detail_pane:
                     placeholder_detail_pane.update("[bold red]CRITICAL ERROR: UI Panes failed to load. Check app.log.[/]")
                return
            
            if not self.articles:
                self.notify("No articles found matching your search criteria", severity="warning")
                logger.warning("No articles found matching search criteria on mount.")
                if current_article_detail_pane:
                    current_article_detail_pane.update("[bold yellow]No articles found![/]\\n\\nTry adjusting your search criteria or time interval.")
                return
                
            logger.debug(f"NewsTUI.on_mount() calling refresh_article_list. current_article_list_pane is: {current_article_list_pane}, current_article_detail_pane is: {current_article_detail_pane}")
            # Pass the queried panes directly
            self.loaded_successfully = self.refresh_article_list(current_article_list_pane, current_article_detail_pane)
            if not self.loaded_successfully:
                logger.error("Problem displaying articles during on_mount. loaded_successfully is False.")
                self.notify("Problem displaying articles. Check log for details.", severity="error")
        except Exception as e:
            logger.error(f"Error initializing TUI on_mount: {str(e)}", exc_info=True)
            self.notify(f"Error initializing: {str(e)}. Check log.", severity="error")
            if current_article_detail_pane:
                current_article_detail_pane.update(f"[bold red]Error loading article list:[/]\\n\\n{str(e)}\\n\\nCheck the log for more details.")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Called when an item in the ListView is selected."""
        try:
            selected_list_item = event.item
            # First check if we can access article_data
            if hasattr(selected_list_item, 'article_data'): 
                article = selected_list_item.article_data
                if article:
                    self.article_detail_pane.selected_article = article
                else:
                    logger.warning("Selected list item has no article_data.")
                    self.article_detail_pane.update("[bold yellow]Selected item has no article data[/]")
            else:
                logger.warning("Selected list item does not have article_data attribute.")
                self.article_detail_pane.update("[bold yellow]Could not load article details[/]")
        except Exception as e:
            logger.error(f"Error displaying article on selection: {str(e)}", exc_info=True)
            self.article_detail_pane.update(f"[bold red]Error displaying article:[/]\n\n{str(e)}")

    def action_cursor_up(self) -> None:
        """Action to move cursor up in the list view."""
        if self.article_list_pane:
            self.article_list_pane.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Action to move cursor down in the list view."""
        if self.article_list_pane:
            self.article_list_pane.action_cursor_down()

    def action_show_filter_menu(self) -> None:
        """Show the filter menu to filter articles by ticker."""
        # Collect all unique tickers from articles
        all_tickers = set()
        for article in self.all_articles:
            if article.tickers:
                all_tickers.update(article.tickers)
        
        if not all_tickers:
            self.notify("No tickers found in articles", severity="warning")
            return
        
        # Create a menu of tickers to filter by
        menu_items = sorted(list(all_tickers))
        
        # Get company names for tickers
        stock_map = fetch_major_stocks()
        
        # Use a modal instead of the notification approach
        class TickerFilterDialog(ModalScreen):
            BINDINGS = [
                ("escape", "dismiss", "Close"),
                ("up", "cursor_up", "Up"),
                ("down", "cursor_down", "Down"),
                ("enter", "select_ticker", "Select")
            ]
            
            def __init__(self, tickers: List[str], parent_tui: "NewsTUI", stock_map: dict):
                super().__init__()
                self.tickers = tickers
                self.parent_tui = parent_tui
                self.selected_index = 0
                self.stock_map = stock_map
                
            def compose(self) -> ComposeResult:
                with Vertical(id="ticker_dialog"):
                    yield Label("Select ticker to filter by:", id="ticker_dialog_title")
                    for i, ticker in enumerate(self.tickers):
                        # Get company name if available
                        company_name = self.stock_map.get(ticker, "")
                        if company_name:
                            button_text = f"{ticker} - {company_name}"
                        else:
                            button_text = ticker
                            
                        btn = Button(button_text, id=f"ticker-{ticker}", classes="ticker-button")
                        # Mark the first button as initially focused
                        if i == 0:
                            btn.add_class("selected")
                        yield btn
                    yield Button("Cancel", id="cancel-button")
            
            def on_button_pressed(self, event: Button.Pressed) -> None:
                button_id = event.button.id
                if button_id == "cancel-button":
                    self.dismiss()
                elif button_id and button_id.startswith("ticker-"):
                    ticker = button_id[7:]  # Remove "ticker-" prefix
                    self.dismiss()
                    # Apply the filter
                    self.parent_tui.filter_by_ticker(ticker)
            
            def on_mount(self) -> None:
                # Focus the first ticker button
                self.query_one("#ticker-" + self.tickers[0], Button).focus()
            
            def action_cursor_up(self) -> None:
                # Move selection up
                buttons = self.query(".ticker-button")
                if not buttons:
                    return
                
                for i, button in enumerate(buttons):
                    if button.has_class("selected"):
                        button.remove_class("selected")
                        new_index = (i - 1) % len(buttons)
                        buttons[new_index].add_class("selected")
                        buttons[new_index].focus()
                        self.selected_index = new_index
                        break
                else:
                    # If no selection, select the last one
                    buttons[-1].add_class("selected")
                    buttons[-1].focus()
                    self.selected_index = len(buttons) - 1
            
            def action_cursor_down(self) -> None:
                # Move selection down
                buttons = self.query(".ticker-button")
                if not buttons:
                    return
                
                for i, button in enumerate(buttons):
                    if button.has_class("selected"):
                        button.remove_class("selected")
                        new_index = (i + 1) % len(buttons)
                        buttons[new_index].add_class("selected")
                        buttons[new_index].focus()
                        self.selected_index = new_index
                        break
                else:
                    # If no selection, select the first one
                    buttons[0].add_class("selected")
                    buttons[0].focus()
                    self.selected_index = 0
            
            def action_select_ticker(self) -> None:
                # Select the currently focused ticker
                buttons = self.query(".ticker-button")
                if buttons and 0 <= self.selected_index < len(buttons):
                    button = buttons[self.selected_index]
                    button_id = button.id
                    if button_id and button_id.startswith("ticker-"):
                        ticker = button_id[7:]  # Remove "ticker-" prefix
                        self.dismiss()
                        # Apply the filter
                        self.parent_tui.filter_by_ticker(ticker)
        
        # Show the ticker dialog
        self.push_screen(TickerFilterDialog(menu_items, self, stock_map))

    def filter_by_ticker(self, ticker: str) -> None:
        """Filter articles to show only those containing the specified ticker."""
        self.current_filter = ticker
        logger.info(f"Filtering by ticker: {ticker}")
        
        # Debug the state before filtering
        logger.debug(f"Before filtering: all_articles={len(self.all_articles)}, current articles={len(self.articles)}")
        logger.debug(f"Filtering for ticker: {ticker}")
        
        # Log the state of all articles and their tickers
        logger.debug("=== ARTICLES BEFORE FILTERING ===")
        for i, article in enumerate(self.all_articles[:5]):
            logger.debug(f"Article {i+1}: {article.title} - Tickers: {article.tickers}")
        
        # Use strict filtering - only show articles where the ticker is explicitly listed
        filtered_articles = [a for a in self.all_articles if a.tickers and ticker in a.tickers]
        
        logger.debug(f"After filtering: found {len(filtered_articles)} articles with ticker {ticker}")
        # Debug the filtered articles to verify tickers
        logger.debug("=== ARTICLES AFTER FILTERING ===")
        for i, article in enumerate(filtered_articles[:5]):
            logger.debug(f"Filtered article {i+1}: Title='{article.title}', Tickers={article.tickers}")
        
        if not filtered_articles:
            self.notify(f"No articles found for ticker {ticker}", severity="warning")
            logger.info(f"No articles found for ticker {ticker} after filtering.")
            return
        
        # Update articles list and refresh the view
        logger.debug("Setting self.articles to filtered articles")
        self.articles = filtered_articles
        logger.debug(f"Length of self.articles after update: {len(self.articles)}")
        success = self.refresh_article_list()
        logger.debug(f"refresh_article_list returned: {success}")
        
        self.notify(f"Filtered to show {len(filtered_articles)} articles for {ticker}", severity="success")
        logger.info(f"Filtered to {len(filtered_articles)} articles for {ticker}.")

    def action_reset_filter(self) -> None:
        """Reset any active filters and show all articles."""
        if self.current_filter:
            self.articles = self.all_articles.copy()
            self.current_filter = None
            self.refresh_article_list()
            self.notify("Filter reset, showing all articles", severity="success")
            logger.info("Filter reset, showing all articles.")
        else:
            self.notify("No active filter", severity="information")
            logger.info("Reset filter called but no active filter.")

    def refresh_article_list(self, list_pane_override: Optional[ListView] = None, detail_pane_override: Optional[ArticleDetailPane] = None) -> bool:
        """Refresh the article list view with current articles.
        Accepts optional overrides for list_pane and detail_pane for robust calling.
        Returns True if articles were loaded successfully, False otherwise.
        """
        # Use overrides if provided, otherwise use self. (though self should be reliable now)
        active_list_pane = list_pane_override if list_pane_override else self.article_list_pane
        active_detail_pane = detail_pane_override if detail_pane_override else self.article_detail_pane
        
        logger.debug(f"refresh_article_list called. active_list_pane: {type(active_list_pane)}, active_detail_pane: {type(active_detail_pane)}")
        logger.debug(f"Current self.articles length: {len(self.articles)}")
        logger.debug(f"Current filter: {self.current_filter}")

        try:
            if active_list_pane is None: # Explicit check for None
                logger.error("Article list pane (active_list_pane) is literally None - unable to refresh")
                return False
            
            # Log the state of the pane before clearing
            logger.debug(f"active_list_pane before clear: {active_list_pane!r}, has children: {bool(active_list_pane.children)}")

            active_list_pane.clear()
            
            logger.debug(f"Refreshing article list with {len(self.articles)} articles using {id(active_list_pane)}")
            
            if not self.articles:
                logger.debug("No articles to display, adding placeholder item")
                placeholder_item = ListItem(Label("No articles found matching your criteria."))
                placeholder_item.disabled = True
                active_list_pane.append(placeholder_item)
                if active_detail_pane:
                    active_detail_pane.selected_article = None
                    active_detail_pane.update("[bold yellow]No articles found matching your criteria[/]")
                logger.info("refresh_article_list: No articles to display.")
                return False

            added_count = 0
            for i, article_item in enumerate(self.articles):
                try:
                    max_title_len = 45
                    date_str = article_item.published_date.strftime('%m-%d %H:%M') if article_item.published_date else "No Date"
                    display_title = article_item.title
                    if len(display_title) > max_title_len:
                        display_title = display_title[:max_title_len - 3] + "..."
                    
                    # Fix: Properly handle ticker formatting without causing Rich markup issues
                    ticker_info = ""
                    if article_item.tickers:
                        # Escape any brackets in tickers to avoid Rich markup errors
                        safe_tickers = [t.replace('[', '\\[').replace(']', '\\]') for t in article_item.tickers]
                        ticker_info = f"[yellow]({', '.join(safe_tickers)})[/]"
                    
                    list_item_label = f"[cyan]{date_str}[/] [bold white]{display_title}[/] {ticker_info}"
                    list_item = ListItem(Label(list_item_label), name=str(i), classes="article-list-item")
                    list_item.article_data = article_item  # type: ignore
                    active_list_pane.append(list_item)
                    added_count += 1
                except Exception as e:
                    self.notify(f"Error with article {i}: {str(e)}", severity="warning")
                    logger.error(f"Error processing article {i} for list view: {e}", exc_info=True)
            
            logger.debug(f"Added {added_count} articles to the list view using {id(active_list_pane)}")
            
            if self.articles and active_list_pane.children:
                logger.debug(f"Setting selection to first article (total: {len(active_list_pane.children)}) using {id(active_list_pane)}")
                active_list_pane.index = 0
                
                first_article_item = active_list_pane.children[0]
                if hasattr(first_article_item, 'article_data') and active_detail_pane:
                    logger.debug("First article has article_data, updating detail pane")
                    active_detail_pane.selected_article = first_article_item.article_data  # type: ignore
                    return True
                else:
                    logger.warning(f"First article doesn't have article_data or active_detail_pane is None. Children: {len(active_list_pane.children) if active_list_pane and active_list_pane.children else 'N/A'}")
            else:
                logger.warning(f"No articles to select in {id(active_list_pane)}! Articles: {len(self.articles)}, Children: {len(active_list_pane.children) if active_list_pane and active_list_pane.children else 'N/A'}")
            
            return len(self.articles) > 0
            
        except Exception as e:
            logger.error(f"Error in refresh_article_list with pane {id(active_list_pane)}: {e}", exc_info=True)
            if active_detail_pane:
                active_detail_pane.update(f"[bold red]Error refreshing article list:[/]\\n\\n{str(e)}")
            return False


def main():
    """Main function to parse arguments and fetch/display news."""
    # Note: Logging is configured at the top of the file
    
    parser = argparse.ArgumentParser(
        description="Finance Stock News Collector. Fetches news from RSS feeds and filters by stock symbols."
    )
    parser.add_argument(
        "--stocks",
        type=str,
        help="Comma-separated list of stock symbols to filter news for (e.g., AAPL,MSFT,GOOG). Leave empty for general news."
    )
    parser.add_argument(
        "--company",
        type=str,
        help="Search for news by company name (e.g., 'Apple', 'Microsoft'). Will be converted to relevant ticker symbols."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25, # Default limit for TUI, can be adjusted
        help="Maximum number of articles to fetch initially (default: 25)."
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with more verbose output."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock articles instead of fetching from real sources (for testing)."
    )

    args = parser.parse_args()

    logger.info(f"Application started with args: {args}")
    # Print welcome message (can be removed if Header is sufficient)
    # print(f"\n{Back.WHITE}{Fore.BLACK}{Style.BRIGHT} Finance Stock News Collector {Style.RESET_ALL}")
    
    stock_symbols_list: Optional[List[str]] = None
    if args.stocks:
        stock_symbols_list = [symbol.strip().upper() for symbol in args.stocks.split(',') if symbol.strip()]
        if stock_symbols_list:
            logger.info(f"Fetching news for stocks: {', '.join(stock_symbols_list)}")
        else:
            logger.warning("No valid stock symbols provided, fetching general news.")
            stock_symbols_list = None 
    elif args.company:
        # Get stock map for company name lookup
        try:
            stock_map = fetch_major_stocks()
            company_name = args.company.lower()
            matched_tickers = []
            
            # Find all tickers whose company names contain the provided string
            for ticker, name in stock_map.items():
                if company_name in name.lower():
                    matched_tickers.append(ticker)
                    logger.info(f"Company name '{args.company}' matched ticker: {ticker} ({name})")
            
            if matched_tickers:
                stock_symbols_list = matched_tickers
                logger.info(f"Fetching news for company '{args.company}' using tickers: {', '.join(matched_tickers)}")
            else:
                logger.warning(f"No tickers found matching company name: '{args.company}'. Fetching general news.")
                stock_symbols_list = None
        except Exception as e:
            logger.error(f"Error looking up company name: {str(e)}. Please install lxml if needed.")
            logger.info("Falling back to direct company name search")
            # Try a simple approach - use the company name as a search term for articles
            stock_symbols_list = None
            # Set debug flag to make detailed matching info visible in logs
            debug_flag = True
    else:
        logger.info("Fetching general finance news (no stock symbols specified)...")

    debug_flag = args.debug if hasattr(args, 'debug') else False
    use_mock = args.mock if hasattr(args, 'mock') else False
    
    # Set logging level based on debug flag
    if debug_flag:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("DEBUG MODE: Starting with verbose logging enabled...")
    
    if use_mock:
        logger.info("Using mock articles instead of fetching from real sources.")
    
    if debug_flag: # This also sets logging level if needed, but basicConfig already set to DEBUG
        logger.info("DEBUG MODE: Starting article fetch...")
        
    articles = fetch_all_news(stock_symbols=stock_symbols_list, source_limit=args.source_limit, use_mock=use_mock)
    
    if debug_flag:
        logger.debug(f"Fetched {len(articles)} total articles before primary filtering/sorting")
    
    articles.sort(key=lambda x: x.published_date if x.published_date else datetime.min, reverse=True)
    
    # Additional strict filtering if specific stocks were requested
    if stock_symbols_list and articles:
        logger.info(f"Applying strict filtering for requested stocks: {stock_symbols_list}")
        original_count = len(articles)
        
        # Only keep articles where one of the requested stocks is the primary ticker
        # or the requested ticker is prominently featured in the article
        strictly_filtered_articles = []
        for article in articles:
            should_include = False
            
            # Check if article has a primary ticker that matches one of the requested symbols
            if hasattr(article, 'primary_ticker') and article.primary_ticker:
                if article.primary_ticker in stock_symbols_list:
                    should_include = True
                    logger.debug(f"Including article '{article.title[:40]}...' - primary ticker {article.primary_ticker} matches request")
            
            # If no primary ticker match, check if article title contains the ticker or company name
            if not should_include and article.tickers:
                for ticker in stock_symbols_list:
                    if ticker in article.tickers:
                        # Check if ticker appears in title (case insensitive)
                        title_lower = article.title.lower() if article.title else ""
                        if ticker.lower() in title_lower or f"${ticker.lower()}" in title_lower:
                            should_include = True
                            logger.debug(f"Including article '{article.title[:40]}...' - ticker {ticker} in title")
                            break
            
            if should_include:
                strictly_filtered_articles.append(article)
        
        articles = strictly_filtered_articles
        logger.info(f"Strict filtering reduced articles from {original_count} to {len(articles)}")
    
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
            logger.info(f"Filtering articles published since: {time_filter}")
            original_count = len(articles)
            articles = [article for article in articles if article.published_date and article.published_date >= time_filter]
            logger.info(f"Filtered down to {len(articles)} articles from {original_count} after time filter.")
            
            if debug_flag:
                if articles:
                    logger.debug(f"First 3 time-filtered articles:")
                    for i, article in enumerate(articles[:3]):
                        ticker_str = ', '.join(article.tickers) if article.tickers else "None"
                        logger.debug(f"{i+1}. {article.title} - {article.published_date} - Tickers: {ticker_str}")
                else:
                    logger.debug("No articles found after time-interval filtering.")

    articles_to_pass_to_tui = articles[:args.limit]
    logger.info(f"Limiting articles to {args.limit}, passing {len(articles_to_pass_to_tui)} to TUI.")
    
    if not articles_to_pass_to_tui and (args.stocks or args.time_interval):
         logger.warning("No news articles found matching specific criteria after filtering and limiting.")
    elif not articles_to_pass_to_tui:
         logger.warning("No news articles found from any source after filtering and limiting.")
    else:
         logger.info(f"Passing {len(articles_to_pass_to_tui)} articles to the TUI.")
         if debug_flag:
             all_tickers_in_tui_set = set()
             for article in articles_to_pass_to_tui:
                 if article.tickers:
                     all_tickers_in_tui_set.update(article.tickers)
             ticker_summary = ', '.join(all_tickers_in_tui_set) if all_tickers_in_tui_set else "None found"
             logger.debug(f"Articles for TUI contain these tickers: {ticker_summary}")
             logger.debug(f"Article data before passing to TUI (first 3):")
             for i, article in enumerate(articles_to_pass_to_tui[:3]):
                 logger.debug(f"  Article {i+1}: Title='{article.title}', Date='{article.published_date}', Source='{article.source}', Tickers='{article.tickers}', Summary Length='{len(article.summary) if article.summary else 0}'")

    logger.info(f"Starting TUI with {len(articles_to_pass_to_tui)} articles...")
    app = NewsTUI(articles=articles_to_pass_to_tui, cli_args=args)
    try:
        app.run()
    except Exception as e:
        logger.critical(f"TUI run failed: {e}", exc_info=True)
    finally:
        logger.info("Application shutdown.")


if __name__ == "__main__":
    main()
