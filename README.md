# Stock News App

A simple Python application that fetches financial news articles from various RSS sources and optionally filters them by stock symbols.

## Setup

1. Create a virtual environment:
```bash
python3 -m venv venv
```

2. Activate the virtual environment:
```bash
# On macOS/Linux
source venv/bin/activate

# On Windows
venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the application with optional parameters:

```bash
# Fetch general financial news (no filtering)
python main.py

# Fetch news related to specific stocks
python main.py --stocks AAPL,MSFT,GOOG

# Limit the number of articles to display
python main.py --limit 5

# Limit the number of news sources to process
python main.py --source-limit 2

# Filter news by publication time
python main.py --time-interval last-4-hours

# Combine multiple options
python main.py --stocks AAPL,MSFT --time-interval today --limit 3
```

### Command-line Options

- `--stocks`: Comma-separated list of stock symbols to filter news for (e.g., AAPL,MSFT,GOOG)
- `--limit`: Maximum number of articles to display (default: 10)
- `--source-limit`: Maximum number of feed sources to process from sources.json
- `--time-interval`: Filter articles by publication time. Available options:
  - `today`: Articles published today (since midnight)
  - `last-hour`: Articles published in the last hour
  - `last-4-hours`: Articles published in the last 4 hours
  - `last-12-hours`: Articles published in the last 12 hours
  - `last-24-hours`: Articles published in the last 24 hours
  - `last-15-minutes`: Articles published in the last 15 minutes
  - `last-30-minutes`: Articles published in the last 30 minutes

## News Sources

News sources are configured in the `sources.json` file. 