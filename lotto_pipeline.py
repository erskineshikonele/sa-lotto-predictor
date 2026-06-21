"""
SA Lotto Predictor — Auto-Update Data Pipeline
================================================
Author  : Erskine Brister Shikonele
Role    : Computer Systems Engineer
Project : SA National Lottery Statistical Analysis Dashboard

Description
-----------
Full pipeline covering:
  1. Scraping latest draw results from the SA National Lottery website
  2. Parsing and decoding concatenated ball strings
  3. Cleaning and validating all draw records
  4. Duplicate detection before inserting new draws
  5. Merging new draws into the historical dataset
  6. Engineering statistical features (frequency, hot, overdue, pairs)
  7. Regenerating dashboard stats inside index.html automatically
  8. Exporting the enhanced CSV

Run modes
---------
  Manual update:
      python lotto_pipeline.py

  Auto-update (called by GitHub Actions):
      python lotto_pipeline.py --auto-update

  Local scheduler (runs every Wed & Sat at 21:30 SAST):
      python lotto_pipeline.py --schedule

  Stats only (no scraping):
      python lotto_pipeline.py --stats-only

Requirements
------------
    pip install pandas numpy requests beautifulsoup4
"""

import re
import sys
import json
import time
import argparse
import logging
from collections import Counter
from itertools import combinations
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("lotto_pipeline")


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

CSV_PATH       = Path("lotteries_enhanced.csv")
DASHBOARD_PATH = Path("index.html")
BALL_COLS      = ["ball1", "ball2", "ball3", "ball4", "ball5", "ball6"]
MAX_BALL       = 52
WORKER_URL     = "https://lotto-results.bristererskine.workers.dev"
SCRAPE_SOURCES = [
    "https://za.lottonumbers.com/lotto/results",
    "https://za.national-lottery.com/lotto/results",
    "https://www.nationallottery.co.za/lotto/results",
]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Supabase — pushes the official result so the check-results Edge
# Function can compare it against saved picks. Set these as GitHub
# Actions secrets; never commit real keys to the repo.
import os
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")



# ─────────────────────────────────────────────
# 1. LOAD DATASET
# ─────────────────────────────────────────────

def load_dataset(path: Path) -> pd.DataFrame:
    """Load CSV, parse dates, sort chronologically."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    df = pd.read_csv(path)
    df["drawDate"] = pd.to_datetime(df["drawDate"])
    df = df.sort_values("drawDate").reset_index(drop=True)
    log.info(f"Loaded {len(df):,} draws  "
             f"({df['drawDate'].min().date()} -> {df['drawDate'].max().date()})")
    return df


# ─────────────────────────────────────────────
# 2. BALL STRING DECODER
# ─────────────────────────────────────────────

def parse_result_string(s: str, n: int = 7, max_val: int = 58):
    """
    Decode a concatenated ball string (no delimiters) into exactly n
    integers each in [1, max_val].

    Uses recursive backtracking — tries every valid 1-digit and 2-digit
    split, collects all complete parses, then prefers parses with all
    unique values (no duplicate balls in one draw).

    Example:
        "451016224525" -> [4, 5, 10, 16, 22, 45, 25]
    """
    def _recurse(s, remaining):
        if remaining == 0:
            return [[]] if s == "" else []
        if not s:
            return []
        results = []
        v1 = int(s[0])
        if 1 <= v1 <= max_val:
            for tail in _recurse(s[1:], remaining - 1):
                results.append([v1] + tail)
        if len(s) >= 2:
            v2 = int(s[:2])
            if 1 <= v2 <= max_val:
                for tail in _recurse(s[2:], remaining - 1):
                    results.append([v2] + tail)
        return results

    all_parses    = _recurse(s, n)
    unique_parses = [p for p in all_parses if len(set(p)) == n]
    if unique_parses:
        return unique_parses[0]
    return all_parses[0] if all_parses else None


# ─────────────────────────────────────────────
# 3. WEB SCRAPER
# ─────────────────────────────────────────────

def _try_nationallottery(session):
    """Scrape from nationallottery.co.za via worker"""
    try:
        html = _fetch_via_worker(SCRAPE_SOURCES[2], session)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        date_el = (
            soup.find("span", class_=re.compile(r"draw.?date", re.I)) or
            soup.find("div",  class_=re.compile(r"draw.?date", re.I))
        )
        ball_els = (
            soup.find_all("span", class_=re.compile(r"ball", re.I)) or
            soup.find_all("div",  class_=re.compile(r"ball", re.I))
        )
        balls = []
        for el in ball_els:
            txt = el.get_text(strip=True)
            if txt.isdigit() and 1 <= int(txt) <= 58:
                balls.append(int(txt))
            if len(balls) == 7:
                break

        if len(balls) >= 6 and date_el:
            draw_date = pd.to_datetime(date_el.get_text(strip=True), dayfirst=True)
            return {
                "drawDate": draw_date.date().isoformat(),
                "balls":    sorted(balls[:6]),
                "bonus":    balls[6] if len(balls) == 7 else 0,
                "source":   "nationallottery.co.za",
            }
    except Exception as e:
        log.debug(f"nationallottery.co.za failed: {e}")
    return None


def _try_lottonumbers(session):
    """Scrape from za.lottonumbers.com via worker"""
    try:
        html = _fetch_via_worker(SCRAPE_SOURCES[0], session)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        for row in soup.find_all("tr")[:5]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            try:
                draw_date = pd.to_datetime(cells[0].get_text(strip=True), dayfirst=True)
            except Exception:
                continue
            ball_els = row.find_all(class_=re.compile(r"ball", re.I))
            balls = []
            for el in ball_els:
                txt = el.get_text(strip=True)
                if txt.isdigit() and 1 <= int(txt) <= 58:
                    balls.append(int(txt))
            if len(balls) >= 6:
                return {
                    "drawDate": draw_date.date().isoformat(),
                    "balls":    sorted(balls[:6]),
                    "bonus":    balls[6] if len(balls) == 7 else 0,
                    "source":   "za.lottonumbers.com",
                }
    except Exception as e:
        log.debug(f"za.lottonumbers.com failed: {e}")
    return None


def _try_national_lottery_com(session):
    """Scrape from za.national-lottery.com via worker"""
    try:
        html = _fetch_via_worker(SCRAPE_SOURCES[1], session)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        spans = soup.find_all("span", class_=re.compile(r"number|ball|result", re.I))
        balls = []
        for sp in spans:
            txt = sp.get_text(strip=True)
            if txt.isdigit() and 1 <= int(txt) <= 58:
                balls.append(int(txt))
            if len(balls) == 7:
                break

        date_candidates = soup.find_all(string=re.compile(r"\d{1,2}\s+\w+\s+\d{4}"))
        draw_date = None
        for d in date_candidates[:3]:
            try:
                draw_date = pd.to_datetime(d.strip(), dayfirst=True)
                break
            except Exception:
                continue

        if len(balls) >= 6 and draw_date:
            return {
                "drawDate": draw_date.date().isoformat(),
                "balls":    sorted(balls[:6]),
                "bonus":    balls[6] if len(balls) == 7 else 0,
                "source":   "za.national-lottery.com",
            }
    except Exception as e:
        log.debug(f"za.national-lottery.com failed: {e}")
    return None


def fetch_from_worker_json(session) -> dict:
    """
    Call the Cloudflare Worker which parses the lottery page and returns clean JSON.
    Returns dict with drawDate, balls, bonus or None on failure.
    """
    try:
        r = session.get(WORKER_URL + "/", timeout=20)
        if r.status_code == 200:
            data = r.json()
            log.info(f"  Worker response: {data}")
            if data.get("status") == "ok":
                return data
            elif data.get("status") == "parse_failed":
                log.warning(f"  Worker parse failed. HTML length: {data.get('htmlLength')}")
                log.warning(f"  Date found: {data.get('dateMatch')}")
                log.warning(f"  Balls found: {data.get('ballsFound')}")
                log.warning(f"  HTML sample: {data.get('htmlSample','')[:500]}")
        else:
            log.warning(f"  Worker returned status {r.status_code}")
    except Exception as e:
        log.warning(f"  Worker JSON fetch failed: {e}")
    return None


def _fetch_via_worker(url: str, session) -> str:
    """
    Fetch a URL through the Cloudflare Worker proxy to bypass IP blocks.
    Falls back to direct request if worker is unavailable.
    """
    try:
        worker_url = f"{WORKER_URL}/?url={requests.utils.quote(url, safe='')}"
        r = session.get(worker_url, timeout=20)
        if r.status_code == 200 and len(r.text) > 500:
            log.info(f"  Fetched via Cloudflare Worker: {url}")
            return r.text
    except Exception as e:
        log.debug(f"Worker fetch failed: {e}")

    # Fallback: direct request
    try:
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            log.info(f"  Fetched directly: {url}")
            return r.text
    except Exception as e:
        log.debug(f"Direct fetch failed: {e}")

    return ""


def fetch_latest_draw():
    """
    Try Cloudflare Worker JSON endpoint first, then fall back to HTML scraping.
    Returns the first successful result as:
        { "drawDate": "2026-06-04", "balls": [...], "bonus": 17, "source": "..." }
    Returns None if all sources fail.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    log.info("Fetching latest draw results via Cloudflare Worker...")

    # Try Worker JSON first (most reliable)
    result = fetch_from_worker_json(session)
    if result:
        log.info(f"  Worker JSON success: {result['drawDate']} -- {result['balls']} + bonus {result['bonus']}")
        return result

    log.info("  Worker JSON failed, trying HTML scrapers...")
    for fn in [_try_lottonumbers, _try_national_lottery_com, _try_nationallottery]:
        result = fn(session)
        if result:
            log.info(f"  Fetched from {result['source']}: "
                     f"{result['drawDate']} -- {result['balls']} + bonus {result['bonus']}")
            return result

    log.warning("  All scrape sources failed.")
    return None


# ─────────────────────────────────────────────
# 4. DUPLICATE CHECK
# ─────────────────────────────────────────────

def is_already_stored(df: pd.DataFrame, draw_date: str) -> bool:
    """Return True if a draw for this date already exists in the dataset."""
    target = pd.to_datetime(draw_date).date()
    return target in df["drawDate"].dt.date.values


# ─────────────────────────────────────────────
# 5. BUILD RECORD & APPEND
# ─────────────────────────────────────────────

def build_record(draw: dict, draw_number: int) -> dict:
    """Convert a scraped draw dict into a full dataset row."""
    balls = draw["balls"]
    bonus = draw.get("bonus", 0)
    return {
        "drawNumber"       : draw_number,
        "drawDate"         : draw["drawDate"],
        "nextDrawDate"     : "",
        "ball1"            : balls[0],  "ball2": balls[1], "ball3": balls[2],
        "ball4"            : balls[3],  "ball5": balls[4], "ball6": balls[5],
        "bonusBall"        : bonus,
        "div1Winners"      : 0, "div1Payout" : 0,
        "div2Winners"      : 0, "div2Payout" : 0,
        "div3Winners"      : 0, "div3Payout" : 0,
        "div4Winners"      : 0, "div4Payout" : 0,
        "div5Winners"      : 0, "div5Payout" : 0,
        "div6Winners"      : 0, "div6Payout" : 0,
        "div7Winners"      : 0, "div7Payout" : 0,
        "div8Winners"      : 0, "div8Payout" : 0,
        "rolloverAmount"   : 0, "rolloverNumber"   : 0,
        "totalPrizePool"   : 0, "totalSales"       : 0,
        "estimatedJackpot" : draw.get("jackpot", 0),
        "guaranteedJackpot": 0,
        "drawMachine"      : "", "ballSet": "", "status": "Results",
        "gpwinners"  : 0, "wcwinners"  : 0, "ncwinners"  : 0,
        "ecwinners"  : 0, "mpwinners"  : 0, "lpwinners"  : 0,
        "fswinners"  : 0, "kznwinners" : 0, "nwwinners"  : 0,
        "winners"    : 0, "millionairs": 0,
    }


def append_draw(df: pd.DataFrame, draw: dict) -> pd.DataFrame:
    """Append a new draw after duplicate check. Returns updated DataFrame."""
    if is_already_stored(df, draw["drawDate"]):
        # Update jackpot if it was 0 and we now have a value
        mask = df["drawDate"] == pd.to_datetime(draw["drawDate"])
        if mask.any() and draw.get("jackpot", 0) > 0:
            current_jackpot = df.loc[mask, "estimatedJackpot"].values[0]
            if pd.isna(current_jackpot) or int(current_jackpot) == 0:
                df.loc[mask, "estimatedJackpot"] = draw["jackpot"]
                log.info(f"  Updated jackpot for {draw['drawDate']}: R{draw['jackpot']:,}")
        else:
            log.info(f"  Draw {draw['drawDate']} already in dataset -- skipping.")
        return df

    next_num = int(df["drawNumber"].max()) + 1
    record   = build_record(draw, next_num)
    new_row  = pd.DataFrame([record])
    new_row["drawDate"] = pd.to_datetime(new_row["drawDate"])

    df = pd.concat([df, new_row], ignore_index=True)
    df = df.sort_values("drawDate").reset_index(drop=True)
    df["drawNumber"] = range(1, len(df) + 1)

    log.info(f"  Added draw #{next_num}: {draw['drawDate']} -- "
             f"{draw['balls']} + bonus {draw.get('bonus', 0)}")
    return df


# ─────────────────────────────────────────────
# 6. STATISTICAL FEATURE ENGINEERING
# ─────────────────────────────────────────────

def compute_frequency(df):
    flat = df[BALL_COLS].values.flatten()
    return dict(sorted(Counter(int(b) for b in flat if 1 <= b <= MAX_BALL).items()))

def compute_hot(df, window=50):
    recent = df.tail(window)[BALL_COLS].values.flatten()
    return [n for n, _ in Counter(int(b) for b in recent if 1 <= b <= MAX_BALL).most_common()]

def compute_overdue(df):
    last_seen = {}
    for idx, row in df.iterrows():
        for col in BALL_COLS:
            v = int(row[col])
            if 1 <= v <= MAX_BALL:
                last_seen[v] = idx
    total  = len(df)
    scores = {n: total - last_seen.get(n, -1) for n in range(1, MAX_BALL + 1)}
    return [n for n, _ in sorted(scores.items(), key=lambda x: -x[1])]

def compute_top_pairs(df, top_n=20):
    counter = Counter()
    for _, row in df.iterrows():
        balls = sorted(int(row[c]) for c in BALL_COLS if 1 <= int(row[c]) <= MAX_BALL)
        for pair in combinations(balls, 2):
            counter[pair] += 1
    return [list(p) for p, _ in counter.most_common(top_n)]

def compute_bonus_frequency(df):
    vals = df["bonusBall"].values
    return dict(sorted(Counter(int(b) for b in vals if 1 <= b <= MAX_BALL).items()))

def compute_recent_draws(df, n=30):
    rows = []
    for _, row in df.tail(n).iterrows():
        balls   = [int(row[c]) for c in BALL_COLS]
        bonus   = int(row["bonusBall"]) if 1 <= int(row["bonusBall"]) <= MAX_BALL else 0
        jackpot = int(row["estimatedJackpot"]) if pd.notna(row["estimatedJackpot"]) else 0
        rows.append([row["drawDate"].strftime("%Y-%m-%d"), sorted(balls), bonus, jackpot])
    return rows

def build_stats(df):
    freq      = compute_frequency(df)
    hot       = compute_hot(df, window=50)
    overdue   = compute_overdue(df)
    top_pairs = compute_top_pairs(df, top_n=20)
    bonus     = compute_bonus_frequency(df)
    recent    = compute_recent_draws(df, n=30)
    top_ball  = max(freq, key=freq.get)
    return {
        "totalDraws"   : len(df),
        "dateFrom"     : df["drawDate"].min().strftime("%b %Y"),
        "dateTo"       : df["drawDate"].max().strftime("%d %b %Y"),
        "mostFrequent" : {"ball": top_ball, "count": freq[top_ball]},
        "hottestNow"   : hot[0],
        "mostOverdue"  : overdue[0],
        "freq"         : freq,
        "hot"          : hot[:15],
        "overdue"      : overdue[:15],
        "topPairs"     : top_pairs,
        "bonusFreq"    : bonus,
        "recentDraws"  : recent,
    }


# ─────────────────────────────────────────────
# 7. REGENERATE DASHBOARD
# ─────────────────────────────────────────────

def update_dashboard(stats: dict, html_path: Path) -> None:
    """
    Inject updated stats into index.html by replacing the JS data block
    between the sentinel comment and the next function/const declaration.
    Also updates the subtitle text and total-draws metric card.
    """
    if not html_path.exists():
        log.warning(f"Dashboard not found at {html_path} -- skipping HTML update.")
        return

    html = html_path.read_text(encoding="utf-8")

    new_block = (
        f"// === UPDATED DATA: {stats['totalDraws']:,} draws through {stats['dateTo']} ===\n"
        f"const FULL_FREQ = {json.dumps(stats['freq'])};\n"
        f"const HOT       = {json.dumps(stats['hot'])};\n"
        f"const OVERDUE   = {json.dumps(stats['overdue'])};\n"
        f"const TOP_PAIRS = {json.dumps(stats['topPairs'])};\n"
        f"const BONUS_FREQ= {json.dumps(stats['bonusFreq'])};\n"
        f"const RECENT_DRAWS = {json.dumps(stats['recentDraws'], indent=2)};"
    )

    # Remove ALL existing data blocks (handles duplicates)
    # First remove any duplicate const blocks that don't have the sentinel
    dup_pattern = re.compile(
        r"\nconst FULL_FREQ = \{1:.*?\];\s*(?=\n(?:const|let|function|//))",
        re.DOTALL,
    )
    html = dup_pattern.sub("\n", html)

    # Now replace the sentinel block
    pattern = re.compile(
        r"// === UPDATED DATA:.*?const RECENT_DRAWS = \[.*?\];",
        re.DOTALL,
    )

    if pattern.search(html):
        html = pattern.sub(lambda m: new_block, html, count=1)
        log.info("  Dashboard data constants updated.")
    else:
        # Sentinel not found - inject before first let/function in script
        inject_pattern = re.compile(r"(\n)(let |function )")
        html = inject_pattern.sub(
            lambda m: f"\n{new_block}\n\n{m.group(2)}", html, count=1
        )
        log.info("  Dashboard data constants injected.")

    # update subtitle line
    html = re.sub(
        r"Updated dataset:.*?draws \(.*?\)",
        f"Updated dataset: {stats['totalDraws']:,} draws "
        f"({stats['dateFrom']} \u2013 {stats['dateTo']})",
        html,
    )
    # update total-draws metric card value
    html = re.sub(
        r"(<div class=\"metric-value\">)\d[\d,]*(</div>)",
        rf"\g<1>{stats['totalDraws']:,}\g<2>",
        html,
        count=1,
    )

    html_path.write_text(html, encoding="utf-8")
    log.info(f"  Dashboard saved -> {html_path}")


# ─────────────────────────────────────────────
# 8. SAVE CSV
# ─────────────────────────────────────────────

def save_dataset(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)
    log.info(f"  Dataset saved -> {path}  ({len(df):,} draws)")


def push_result_to_supabase(draw: dict) -> None:
    """
    Push the latest official result into the Supabase `results` table
    so the check-results Edge Function has data to compare saved
    picks against. Silently skips if Supabase credentials aren't set
    (keeps the pipeline working even before this feature is configured).
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        log.info("  Supabase not configured -- skipping results push "
                 "(saved-picks feature inactive).")
        return

    try:
        url = f"{SUPABASE_URL}/rest/v1/results"
        headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        payload = {
            "draw_date": draw["drawDate"],
            "balls": draw["balls"],
            "bonus": draw.get("bonus", 0),
            "jackpot": draw.get("jackpot", 0),
        }
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code in (200, 201, 204):
            log.info(f"  Pushed result to Supabase: {draw['drawDate']}")
        else:
            log.warning(f"  Supabase push failed ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        log.warning(f"  Supabase push error: {e}")


# ─────────────────────────────────────────────
# 9. FULL UPDATE CYCLE
# ─────────────────────────────────────────────

def run_update(csv_path=CSV_PATH, html_path=DASHBOARD_PATH) -> bool:
    """
    Full update cycle:
      Load -> Scrape -> Duplicate check -> Append ->
      Recompute stats -> Update dashboard -> Save CSV -> Push to Supabase

    Returns True if a new draw was added, False otherwise.
    """
    log.info("=" * 52)
    log.info("  SA Lotto Predictor -- Auto-Update Pipeline")
    log.info("  Erskine Brister Shikonele  |  CSE")
    log.info("=" * 52)

    df           = load_dataset(csv_path)
    original_len = len(df)

    draw = fetch_latest_draw()
    if draw is None:
        log.error("Could not fetch latest draw. Aborting.")
        return False

    df = append_draw(df, draw)

    if len(df) == original_len:
        # Check if jackpot was updated
        mask = df["drawDate"] == pd.to_datetime(draw["drawDate"])
        if mask.any() and draw.get("jackpot", 0) > 0:
            current = df.loc[mask, "estimatedJackpot"].values[0]
            if pd.notna(current) and int(current) > 0:
                log.info("Jackpot updated — rebuilding dashboard...")
                stats = build_stats(df)
                update_dashboard(stats, html_path)
                save_dataset(df, csv_path)
                push_result_to_supabase(draw)
                return True
        log.info("Dataset is already up to date.")
        return False

    log.info("Recomputing statistics...")
    stats = build_stats(df)

    log.info("Updating dashboard...")
    update_dashboard(stats, html_path)

    log.info("Saving dataset...")
    save_dataset(df, csv_path)

    log.info("Pushing result to Supabase (for saved-picks checking)...")
    push_result_to_supabase(draw)

    log.info(f"\nUpdate complete. Dataset now has {len(df):,} draws.")
    return True


# ─────────────────────────────────────────────
# 10. LOCAL SCHEDULER
# ─────────────────────────────────────────────

def run_scheduler():
    """
    Run locally on a schedule: every Wednesday and Saturday at 21:30 SAST.
    Keeps the process alive and checks every 60 seconds.

    Usage:
        python lotto_pipeline.py --schedule
    """
    try:
        import schedule
    except ImportError:
        log.error("Install schedule first: pip install schedule")
        sys.exit(1)

    log.info("Local scheduler started.")
    log.info("  Runs: Wednesday 21:30 and Saturday 21:30 (SAST)")

    schedule.every().wednesday.at("21:30").do(run_update)
    schedule.every().saturday.at("21:30").do(run_update)

    while True:
        schedule.run_pending()
        time.sleep(60)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SA Lotto Predictor Data Pipeline")
    parser.add_argument("--auto-update", action="store_true",
                        help="Single update cycle (used by GitHub Actions)")
    parser.add_argument("--schedule",    action="store_true",
                        help="Local scheduler (Wed & Sat 21:30 SAST)")
    parser.add_argument("--stats-only",  action="store_true",
                        help="Print stats only, no scraping")
    args = parser.parse_args()

    if args.schedule:
        run_scheduler()
    elif args.stats_only:
        df    = load_dataset(CSV_PATH)
        stats = build_stats(df)
        log.info(f"Total draws   : {stats['totalDraws']:,}")
        log.info(f"Hot top 10    : {stats['hot'][:10]}")
        log.info(f"Overdue top 10: {stats['overdue'][:10]}")
        log.info(f"Most frequent : #{stats['mostFrequent']['ball']} "
                 f"({stats['mostFrequent']['count']} times)")
    else:
        run_update()
