# -*- coding: utf-8 -*-
# Türkei-Feed: nur frische Artikel, robuste Datumsprüfung, Timeout & Logging

import socket, re, hashlib
from typing import Optional, Dict, Any, List
import feedparser
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone, timedelta
from dateutil import parser as dtp

# ---- Einstellungen (anpassbar) ----
MAX_AGE_DAYS = 14          # nur Einträge der letzten X Tage
MAX_ITEMS = 150            # maximal so viele Items im RSS
HTTP_TIMEOUT = 10          # Sek. Timeout pro Feed
USER_AGENT = {"User-Agent": "turkey-feed/1.0 (+https://example.local)"}

# Netz-Timeout global setzen
socket.setdefaulttimeout(HTTP_TIMEOUT)

# Quellen
FEEDS = [
    "https://www.tagesschau.de/infoservices/alle-meldungen-100~rss2.xml",
    "https://www.bundesregierung.de/service/rss/breg-de/1151246/feed.xml",
    "https://www.bundesregierung.de/service/rss/breg-de/2318648/feed.xml",
    "https://www.deutschlandfunk.de/nachrichten-100.rss",
    "https://www.deutschlandfunk.de/politikportal-100.rss",
    "https://www.deutschlandfunk.de/wirtschaft-106.rss",
    "https://www.deutschlandfunk.de/wissen-106.rss",
    "https://www.deutschlandfunk.de/kulturportal-100.rss",
    "https://www.deutschlandfunk.de/europa-112.rss",
    "https://www.deutschlandfunk.de/gesellschaft-106.rss",
    "https://www.deutschlandfunk.de/sportportal-100.rss",
    "https://www.deutschlandfunkkultur.de/politik-114.rss",
    "https://www.deutschlandfunkkultur.de/buecher-108.rss",
    "https://www.deutschlandfunkkultur.de/musikportal-100.rss",
    "https://www.deutschlandfunkkultur.de/wissenschaft-108.rss",
    "https://www.deutschlandfunkkultur.de/meinung-debatte-100.rss",
    "https://www.deutschlandfunkkultur.de/umwelt-104.rss",
    "https://www.deutschlandfunkkultur.de/philosophie-104.rss",
    "https://www.deutschlandfunkkultur.de/psychologie-100.rss",
    "https://www.deutschlandfunkkultur.de/geschichte-136.rss",
    "https://www.deutschlandfunkkultur.de/leben-108.rss",
    "https://www.deutschlandfunkkultur.de/buehne-100.rss",
    "https://www.deutschlandfunkkultur.de/film-serie-100.rss",
]

# --- Türkei-Erkennung ---
COUNTRY_PAT = re.compile(r"\b(türkei|turkei|türkiye|turkey)\b", re.IGNORECASE)
TURKISH_ADJ_PAT = re.compile(
    r"\b("
    r"türkisch(?:e[rsnm]?|en|er)?|tuerkisch(?:e[rsnm]?|en|er)?|"
    r"türke|tuerke|türkin|tuerkin"
    r")\b",
    re.IGNORECASE,
)
GAZETTEER = {
    "istanbul","ankara","izmir","bursa","antalya","adana","konya","gaziantep","kayseri","mersin",
    "eskisehir","eskişehir","diyarbakir","diyarbakır","sanliurfa","şanlıurfa","trabzon","van",
    "erzurum","malatya","manisa","balikesir","balıkesir","denizli","tekirdag","tekirdağ","sivas",
    "hatay","mardin","batman","sirnak","şırnak","bodrum","marmaris","cesme","çeşme","alanya",
    "fethiye","kapadokya","kappadokien","cappadocia"
}
DOMAIN_HINTS = (".tr/", "//tr.", ".tr?")

def looks_like_turkey(title: str, summary: str, link: str) -> bool:
    text = f" {title} {summary} ".lower()
    if TURKISH_ADJ_PAT.search(text):  # dein "immer nehmen"
        return True
    if COUNTRY_PAT.search(text):
        return True
    if any(f" {k} " in f" {text} " for k in GAZETTEER):
        return True
    if any(h in link.lower() for h in DOMAIN_HINTS):
        return True
    return False

# --- Datumshandling ---
def parse_date_from_entry(e: Dict[str, Any]) -> Optional[datetime]:
    """
    Liefert UTC-datetime oder None.
    Filtert unplausible Jahre raus (z.B. 20024).
    """
    now = datetime.now(timezone.utc)
    max_year = now.year + 1  # etwas Toleranz
    # 1) strukturierte Felder von feedparser nutzen
    for key in ("published_parsed", "updated_parsed"):
        st = e.get(key)
        if st:
            try:
                dt = datetime(*st[:6], tzinfo=timezone.utc)
                if 2000 <= dt.year <= max_year:
                    return dt
            except Exception:
                pass
    # 2) Textfelder
    for key in ("published", "updated"):
        s = e.get(key)
        if not s:
            continue
        try:
            dt = dtp.parse(s)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            if 2000 <= dt.year <= max_year:
                return dt
        except Exception:
            continue
    return None

def is_recent(dt: Optional[datetime]) -> bool:
    if not dt:
        return False
    return (datetime.now(timezone.utc) - dt) <= timedelta(days=MAX_AGE_DAYS)

def log(msg: str) -> None:
    print(msg, flush=True)

def build_feed() -> None:
    fg = FeedGenerator()
    fg.id("https://mickymoses.github.io/turkeyfeed/turkey.xml")
    fg.title("Türkei – gefilterte Meldungen (nur aktuell)")
    fg.link(href="https://mickymoses.github.io/turkeyfeed/turkey.xml", rel="self")
    fg.description(f"Automatisch gefilterte Meldungen mit Türkei-Bezug. Nur die letzten {MAX_AGE_DAYS} Tage.")
    fg.language("de")

    seen: set[str] = set()
    items: List[Dict[str, Any]] = []

    for url in FEEDS:
        log(f"→ Hole: {url}")
        try:
            feed = feedparser.parse(url, request_headers=USER_AGENT)
        except Exception as ex:
            log(f"   ⚠️ Abruffehler: {ex}")
            continue

        if getattr(feed, "bozo", 0):
            log(f"   ⚠️ Warnung (bozo): {getattr(feed, 'bozo_exception', '')}")

        source = getattr(feed, "feed", {}).get("title", url)
        start_count = len(items)

        for e in getattr(feed, "entries", []):
            title = e.get("title") or ""
            summary = e.get("summary") or e.get("subtitle", "") or ""
            link = e.get("link") or ""
            if not title and not summary:
                continue
            if not looks_like_turkey(title, summary, link):
                continue

            pub = parse_date_from_entry(e)
            if not is_recent(pub):
                continue  # zu alt oder kein valides Datum

            h = hashlib.sha256((title + link).encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)

            items.append({
                "title": title, "link": link, "summary": summary,
                "source": source, "published": pub
            })

        log(f"   ✓ {len(items) - start_count} frische Treffer")

    # sortieren (neueste zuerst) und begrenzen
    items.sort(key=lambda x: x["published"] or datetime.min.replace(tzinfo=timezone.utc), 
reverse=True)
    items = items[:MAX_ITEMS]

    # in RSS schreiben
    for it in items:
        fe = fg.add_entry()
        fe.id(it["link"])
        fe.title(it["title"])
        desc = (it["summary"] or "").strip()
        if it["source"]:
            desc = f"{it['source']}: {desc}"
        fe.description(desc)
        fe.link(href=it["link"])
        if it["published"]:
            fe.published(it["published"])

    fg.rss_file("turkey.xml", pretty=True)
    log(f"✅ RSS geschrieben: turkey.xml (Items: {len(items)})")

if __name__ == "__main__":
    build_feed()

