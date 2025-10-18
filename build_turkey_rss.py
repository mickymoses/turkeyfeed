import feedparser, re, hashlib, socket, sys, time
from dateutil import parser as dtp
from datetime import datetime, timezone
from feedgen.feed import FeedGenerator

# --- Netz: harter Timeout für alle Verbindungen (in Sekunden) ---
socket.setdefaulttimeout(10)

# Eigener User-Agent (manche Server blocken "Python-urllib")
USER_AGENT = {"User-Agent": "turkey-feed/1.0 (+https://example.local)"}

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
    if TURKISH_ADJ_PAT.search(text): return True   # immer nehmen
    if COUNTRY_PAT.search(text): return True
    if any(f" {k} " in f" {text} " for k in GAZETTEER): return True
    if any(h in link.lower() for h in DOMAIN_HINTS): return True
    return False

def parse_date(s):
    if not s: return None
    try:
        dt = dtp.parse(s)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def log(msg):
    print(msg, flush=True)

def build_feed():
    fg = FeedGenerator()
    fg.id("http://localhost:8080/turkey.xml")
    fg.title("Türkei – gefilterte Meldungen")
    fg.link(href="http://localhost:8080/turkey.xml", rel="self")
    fg.description("Automatisch gefilterte Meldungen mit Türkei-Bezug.")
    fg.language("de")

    seen = set()
    items = []

    for url in FEEDS:
        log(f"→ Hole: {url}")
        try:
            feed = feedparser.parse(url, request_headers=USER_AGENT)
        except Exception as ex:
            log(f"   ⚠️ Fehler beim Abruf: {ex}")
            continue

        # feed.bozo == 1 => Parsing-Problem; trotzdem evtl. Einträge vorhanden
        if getattr(feed, "bozo", 0):
            log(f"   ⚠️ Warnung (bozo): {getattr(feed, 'bozo_exception', '')}")

        source = feed.feed.get("title", url) if hasattr(feed, "feed") else url
        count_before = len(items)

        for e in getattr(feed, "entries", []):
            title = e.get("title") or ""
            summary = e.get("summary") or e.get("subtitle", "") or ""
            link = e.get("link") or ""
            if not title and not summary:
                continue
            if not looks_like_turkey(title, summary, link):
                continue
            h = hashlib.sha256((title + link).encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            pub = parse_date(e.get("published") or e.get("updated"))
            items.append({"title": title, "link": link, "summary": summary, 
"source": source, "published": pub})

        log(f"   ✓ {len(items) - count_before} Treffer aus dieser Quelle")

    # Sortierung & Feed bauen
    items.sort(key=lambda x: x["published"] or 
datetime.min.replace(tzinfo=timezone.utc), reverse=True)

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
    log(f"✅ RSS geschrieben: turkey.xml  (Items: {len(items)})")

if __name__ == "__main__":
    build_feed()

