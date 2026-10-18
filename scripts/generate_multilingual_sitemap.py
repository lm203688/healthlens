#!/usr/bin/env python3
"""
Sitemap Multi-language Generator
Generates hreflang-safe sitemap with zh-CN + en-US entries for each page.
Usage: python scripts/generate_multilingual_sitemap.py
"""
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

BASE_URL = "https://healthlens.cc"
LANGUAGES = ["zh-CN", "en-US"]

def extract_urls(sitemap_xml: str) -> list[str]:
    """Extract all <loc> URLs from sitemap XML."""
    return re.findall(r"<loc>(https?://[^\s<]+)</loc>", sitemap_xml)

def detect_lang(url: str) -> str:
    """Detect language from URL path or content patterns."""
    if "/en/" in url or "/en-" in url:
        return "en-US"
    if "/zh/" in url:
        return "zh-CN"
    # Default to Chinese for HealthLens URLs
    return "zh-CN"

def generate_hreflang_alternates(zh_urls: list[str], en_urls: list[str]) -> str:
    """Generate sitemap entries with hreflang alternates."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"')
    lines.append('        xmlns:xhtml="http://www.w3.org/1999/xhtml">')

    # Group by base path
    all_urls = set(zh_urls + en_urls)
    for url in sorted(all_urls):
        lang = detect_lang(url)
        lines.append('  <url>')
        lines.append(f'    <loc>{url}</loc>')
        lines.append(f'    <xhtml:link rel="alternate" hreflang="{lang}" href="{url}"/>')

        # Add alternate for other language
        for alt_lang in LANGUAGES:
            if alt_lang != lang:
                alt_url = url.replace("/zh-CN/", f"/{alt_lang}/").replace("/zh/", f"/{alt_lang}/")
                if alt_url != url:
                    lines.append(f'    <xhtml:link rel="alternate" hreflang="{alt_lang}" href="{alt_url}"/>')
        lines.append('  </url>')

    lines.append('</urlset>')
    return '\n'.join(lines)

if __name__ == "__main__":
    sitemap_path = Path(__file__).parent.parent / "app" / "api" / "seo.py"
    # Read from deployed sitemap or use static list
    print("Generating multilingual sitemap...")
    # This is a placeholder - actual implementation would fetch from CF Pages
    print("Run: curl https://healthlens.cc/sitemap.xml > sitemap_zh.xml")
    print("Then run this script to generate multilingual version")
