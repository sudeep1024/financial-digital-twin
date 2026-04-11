from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime


POSITIVE_TERMS = {
    "beat",
    "beats",
    "growth",
    "upgrade",
    "strong",
    "surge",
    "record",
    "profit",
    "expansion",
    "outperform",
    "optimistic",
    "gain",
    "rally",
}

NEGATIVE_TERMS = {
    "miss",
    "misses",
    "downgrade",
    "weak",
    "fall",
    "slump",
    "loss",
    "cut",
    "risk",
    "lawsuit",
    "default",
    "decline",
    "drop",
    "warning",
}


def _sentiment(title: str) -> tuple[float, str]:
    cleaned = re.sub(r"[^a-zA-Z0-9\\s]", " ", title.lower())
    words = [w for w in cleaned.split() if w]
    if not words:
        return 0.0, "neutral"

    pos = sum(1 for word in words if word in POSITIVE_TERMS)
    neg = sum(1 for word in words if word in NEGATIVE_TERMS)
    score = (pos - neg) / max(len(words), 1)

    if score > 0.04:
        label = "positive"
    elif score < -0.04:
        label = "negative"
    else:
        label = "neutral"
    return round(score, 4), label


def _fetch_google_news_rss(query: str, limit: int = 8) -> list[dict]:
    encoded_query = urllib.parse.quote_plus(query)
    url = (
        "https://news.google.com/rss/search"
        f"?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (FinancialDigitalTwin/1.0)"
        },
    )

    with urllib.request.urlopen(req, timeout=8) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = html.unescape(item.findtext("title", default="")).strip()
        link = item.findtext("link", default="").strip()
        published = item.findtext("pubDate", default="").strip()
        source = item.findtext("source", default="Google News").strip()
        sentiment_score, sentiment = _sentiment(title)

        items.append(
            {
                "title": title,
                "link": link,
                "published_at": published,
                "source": source or "Google News",
                "sentiment": sentiment,
                "sentiment_score": float(sentiment_score),
            }
        )
    return items


def get_news_feed(ticker: str = "HDFCBANK.NS") -> dict:
    company_query = f"{ticker} company earnings valuation"
    macro_query = "global economy inflation rates monetary policy recession growth"

    try:
        company_news = _fetch_google_news_rss(company_query, limit=8)
    except Exception:
        company_news = []

    try:
        macro_news = _fetch_google_news_rss(macro_query, limit=8)
    except Exception:
        macro_news = []

    all_items = company_news + macro_news
    aggregate_sentiment = (
        sum(item["sentiment_score"] for item in all_items) / len(all_items)
        if all_items
        else 0.0
    )

    return {
        "ticker": ticker,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sentiment_score": float(round(aggregate_sentiment, 4)),
        "company_news": company_news,
        "macro_news": macro_news,
    }
