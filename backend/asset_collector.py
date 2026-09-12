from __future__ import annotations

import mimetypes
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class _ImageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []
        self.social_images: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "img":
            src = attrs.get("src") or attrs.get("data-src")
            if src:
                self.urls.append(src)
            srcset = attrs.get("srcset") or attrs.get("data-srcset")
            if srcset:
                for item in srcset.split(","):
                    candidate = item.strip().split(" ")[0]
                    if candidate:
                        self.urls.append(candidate)
        if tag.lower() == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key in {"og:image", "twitter:image"} and attrs.get("content"):
                self.social_images.append(attrs["content"])


def _extension(content_type: str, url: str) -> str:
    ctype = (content_type or "").split(";")[0].strip().lower()
    ext = mimetypes.guess_extension(ctype) or Path(urlparse(url).path).suffix.lower()
    if ext == ".jpe":
        ext = ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = ".jpg"
    return ext


def collect_source_images(
    source_url: str,
    assets_dir: Path,
    max_images: int = 8,
) -> list[str]:
    """
    Best-effort collection of image assets already published on a customer's source website.

    This is intended for an owner-consented rebuild/demo. A real production job must still confirm
    that the customer has rights to reuse the assets before launch. Failures are non-fatal.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    req = Request(
        source_url,
        headers={
            "User-Agent": "DarwinIndustriesWebsiteStudio/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            html = response.read(2_000_000).decode("utf-8", errors="ignore")
    except Exception:
        return []

    parser = _ImageParser()
    parser.feed(html)

    urls: list[str] = []
    for raw in parser.social_images + parser.urls:
        absolute = urljoin(source_url, raw)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if absolute not in urls:
            urls.append(absolute)

    saved: list[str] = []
    for url in urls:
        if len(saved) >= max_images:
            break
        try:
            image_req = Request(
                url,
                headers={
                    "User-Agent": "DarwinIndustriesWebsiteStudio/1.0",
                    "Referer": source_url,
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
            )
            with urlopen(image_req, timeout=20) as response:
                content_type = response.headers.get("Content-Type", "")
                if not content_type.lower().startswith("image/"):
                    continue
                data = response.read(4_000_001)
                if not data or len(data) > 4_000_000:
                    continue
                # Avoid tiny icons/tracking pixels becoming hero/product artwork.
                if len(data) < 15_000:
                    continue
                lower_url = url.lower()
                if any(token in lower_url for token in ("favicon", "icon-", "sprite", "tracking", "pixel")):
                    continue
                ext = _extension(content_type, url)
                filename = f"customer-{len(saved)+1:02d}{ext}"
                (assets_dir / filename).write_bytes(data)
                saved.append(f"assets/{filename}")
        except Exception:
            continue

    return saved
