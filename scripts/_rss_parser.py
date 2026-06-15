# -*- coding: utf-8 -*-
"""
Lightweight RSS/Atom parser using stdlib only.
Fallback for environments where feedparser is broken.
"""
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any


NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'media': 'http://search.yahoo.com/mrss/',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'content': 'http://purl.org/rss/1.0/modules/content/',
}


def _text(el, *tags):
    for tag in tags:
        child = el.find(tag, NS)
        if child is not None and child.text:
            return child.text.strip()
    return ''


def _attr_or_text(el, tag, attr='href'):
    child = el.find(tag, NS)
    if child is None:
        return ''
    return child.get(attr, '') or (child.text or '').strip()


def parse(url: str, timeout: int = 15) -> Any:
    """Parse RSS/Atom feed. Returns an object with .entries list."""

    class Entry:
        def __init__(self, **kw):
            self.__dict__.update(kw)
            self.tags = []

        def get(self, key, default=''):
            return self.__dict__.get(key, default)

    class Feed:
        def __init__(self):
            self.entries = []

    feed = Feed()
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; HubCaptacao/1.0)'
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
    except Exception:
        return feed

    tag = root.tag
    # RSS 2.0
    if 'rss' in tag or root.find('channel') is not None:
        channel = root.find('channel') or root
        for item in channel.findall('item'):
            title   = _text(item, 'title')
            link    = _text(item, 'link') or _attr_or_text(item, 'atom:link')
            summary = _text(item, 'description', 'content:encoded')
            pubdate = _text(item, 'pubDate', 'dc:date')
            cats    = [c.text.strip() for c in item.findall('category') if c.text]
            e = Entry(title=title, link=link, summary=summary, published=pubdate)
            e.tags = [{'term': c} for c in cats]
            feed.entries.append(e)
    # Atom
    elif 'Atom' in tag or '{http://www.w3.org/2005/Atom}' in tag:
        ns = 'http://www.w3.org/2005/Atom'
        for item in root.findall(f'{{{ns}}}entry'):
            title   = _text(item, f'{{{ns}}}title')
            link_el = item.find(f'{{{ns}}}link')
            link    = link_el.get('href', '') if link_el is not None else ''
            summary = _text(item, f'{{{ns}}}summary', f'{{{ns}}}content')
            pubdate = _text(item, f'{{{ns}}}published', f'{{{ns}}}updated')
            e = Entry(title=title, link=link, summary=summary, published=pubdate)
            feed.entries.append(e)

    return feed
