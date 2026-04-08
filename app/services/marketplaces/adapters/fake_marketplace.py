"""Fake Playwright marketplace adapter used to demonstrate the scraper architecture."""

from __future__ import annotations

from html import unescape
from urllib.parse import quote
import re

from app.services.marketplaces.base import BasePlaywrightMarketplaceAdapter
from app.services.marketplaces.parsing import MarketplaceParser
from app.services.marketplaces.types import PageFetchResult
from app.services.providers import RawSourceItem


class FakeMarketplaceParser(MarketplaceParser):
    """Parser for a tiny fake marketplace HTML layout."""

    _CARD_PATTERN = re.compile(
        r'<article\s+data-id="(?P<item_id>[^"]+)">\s*'
        r"<h2>(?P<title>.*?)</h2>\s*"
        r'<p\s+class="subtitle">(?P<subtitle>.*?)</p>\s*'
        r'<p\s+class="author">(?P<author>.*?)</p>\s*'
        r'<p\s+class="category">(?P<category>.*?)</p>\s*'
        r'<p\s+class="description">(?P<description>.*?)</p>\s*'
        r'<a\s+href="(?P<url>[^"]+)">.*?</a>\s*'
        r"</article>",
        re.IGNORECASE | re.DOTALL,
    )

    def parse(self, artifact: PageFetchResult) -> list[RawSourceItem]:
        html = artifact.html or ""
        items: list[RawSourceItem] = []
        for match in self._CARD_PATTERN.finditer(html):
            item_id = match.group("item_id").strip()
            title = unescape(match.group("title")).strip()
            subtitle = unescape(match.group("subtitle")).strip() or None
            author = unescape(match.group("author")).strip()
            category = unescape(match.group("category")).strip()
            description = unescape(match.group("description")).strip() or None
            url = unescape(match.group("url")).strip()
            items.append(
                RawSourceItem(
                    provider_name=artifact.adapter_name,
                    query_text=artifact.query.text,
                    query_kind=artifact.query.kind,
                    provider_item_id=item_id,
                    dedupe_key=item_id,
                    source_url=url,
                    title=title,
                    subtitle=subtitle,
                    authors=[author] if author else [],
                    categories=[category] if category else [],
                    description_text=description,
                    content_text="\n".join(part for part in [title, subtitle or "", author, category, description or ""] if part),
                    published_date_raw=None,
                    average_rating=None,
                    rating_count=None,
                    review_count=None,
                    raw_payload={
                        "adapter_name": artifact.adapter_name,
                        "requested_url": artifact.requested_url,
                        "final_url": artifact.final_url,
                        "snapshot_html_path": artifact.snapshot.html_path,
                    },
                )
            )
        return items


class FakeMarketplaceAdapter(BasePlaywrightMarketplaceAdapter):
    """Example adapter proving the navigation/parser separation."""

    provider_name = "fake_marketplace"

    def __init__(self) -> None:
        super().__init__(parser=FakeMarketplaceParser())

    def build_entry_urls(self, query) -> list[str]:
        html = f"""
        <html>
          <body>
            <article data-id="fake-1">
              <h2>{query.text.title()} Spotlight</h2>
              <p class="subtitle">Demo Listing</p>
              <p class="author">Demo Author</p>
              <p class="category">Demo Category</p>
              <p class="description">Synthetic adapter page for architecture validation.</p>
              <a href="https://example.test/fake-1">View</a>
            </article>
          </body>
        </html>
        """.strip()
        return [f"data:text/html,{quote(html)}"]
