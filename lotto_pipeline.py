"""
SA Lotto Predictor — Data Pipeline
====================================
Author  : Erskine Brister Shikonele
Role    : Computer Systems Engineer
Project : SA National Lottery Statistical Analysis Dashboard

Description
-----------
This script covers the full pipeline used to:
  1. Load and inspect the raw lottery dataset
  2. Parse and decode concatenated ball strings from the lottery archive
  3. Clean and validate all draw records
  4. Extend the dataset with new draws (Nov 2024 → May 2026)
  5. Engineer statistical features (frequency, hot, overdue, pairs)
  6. Export the enhanced dataset to CSV for use in the dashboard

Requirements
------------
    pip install pandas numpy
"""

import pandas as pd
import numpy as np
from collections import Counter
from itertools import combinations


# ─────────────────────────────────────────────
# 1. LOAD RAW DATASET
# ─────────────────────────────────────────────

def load_raw(path: str) -> pd.DataFrame:
    """
    Load the original CSV exported from the SA National Lottery archive.
    Parses drawDate as datetime and sorts chronologically.
    """
    df = pd.read_csv(path)
    df['drawDate'] = pd.to_datetime(df['drawDate'])
    df = df.sort_values('drawDate').reset_index(drop=True)

    print(f"Loaded {len(df):,} draws")
    print(f"Date range : {df['drawDate'].min().date()} → {df['drawDate'].max().date()}")
    print(f"Columns    : {list(df.columns)}\n")
    return df


# ─────────────────────────────────────────────
# 2. BALL STRING DECODER
# ─────────────────────────────────────────────

def parse_result_string(s: str, n: int = 7, max_val: int = 58) -> list | None:
    """
    Decode a concatenated ball string from the lottery archive into
    a list of n integers, each in range [1, max_val].

    The archive stores results as raw digit strings with no delimiters,
    e.g. "451016224525" → [4, 5, 10, 16, 22, 45, 25]

    Strategy: recursive backtracking — try all valid 1-digit and 2-digit
    splits at each position, collect all parses that consume the full string
    into exactly n numbers, then prefer parses where all numbers are unique
    (no duplicate balls in a single draw).

    Args:
        s       : raw result string from archive
        n       : expected number of values (default 7 = 6 balls + bonus)
        max_val : upper bound of valid ball numbers (52 or 58 post-expansion)

    Returns:
        List of n integers, or None if no valid parse exists.
    """
    def _recurse(s: str, remaining: int) -> list[list[int]]:
        if remaining == 0:
            return [[]] if s == '' else []
        if s == '':
            return []

        results = []

        # try 1-digit parse
        v1 = int(s[0])
        if 1 <= v1 <= max_val:
            for tail in _recurse(s[1:], remaining - 1):
                results.append([v1] + tail)

        # try 2-digit parse
        if len(s) >= 2:
            v2 = int(s[:2])
            if 1 <= v2 <= max_val:
                for tail in _recurse(s[2:], remaining - 1):
                    results.append([v2] + tail)

        return results

    all_parses = _recurse(s, n)

    # prefer parses with all-unique values (no duplicate balls)
    unique_parses = [p for p in all_parses if len(set(p)) == n]
    if unique_parses:
        return unique_parses[0]

    return all_parses[0] if all_parses else None


# ─────────────────────────────────────────────
# 3. BUILD NEW DRAW RECORDS
# ─────────────────────────────────────────────

# Raw draw data scraped from za.national-lottery.com and za.lottonumbers.com
# Format: (date_str, result_string, estimated_jackpot_rands)
NEW_DRAWS_RAW = [
    # ── 2025 Q1 ──────────────────────────────
    ("2025-01-04", "5111319365215",  7_000_000),
    ("2025-01-08", "3141824485714",  9_000_000),
    ("2025-01-11", "19293035394517", 11_000_000),
    ("2025-01-15", "3923364044513",  13_000_000),
    ("2025-01-18", "131926273748",   15_000_000),
    ("2025-01-22", "418203241457",   17_000_000),
    ("2025-01-25", "6152535374538",  19_000_000),
    ("2025-01-29", "5111834455030",  21_000_000),
    ("2025-02-01", "6242944485523",  23_000_000),
    ("2025-02-05", "7131921334839",  25_000_000),
    ("2025-02-08", "19303444515327", 28_000_000),
    ("2025-02-12", "8142128354442",  30_000_000),
    ("2025-02-15", "4121622414950",  32_000_000),
    ("2025-02-19", "3162637484943",  34_000_000),
    ("2025-02-22", "1927374143556",  36_000_000),
    ("2025-02-26", "8162334384015",  38_000_000),
    ("2025-03-01", "2193137405119",  40_000_000),
    ("2025-03-05", "7102029364543",  42_000_000),
    ("2025-03-08", "3152228364950",  44_000_000),
    ("2025-03-12", "19253236474221", 46_000_000),
    ("2025-03-15", "5131722344533",  48_000_000),
    ("2025-03-19", "916243148511",   50_000_000),
    ("2025-03-22", "4202834394714",  52_000_000),
    ("2025-03-26", "1121824304015",  54_000_000),
    ("2025-03-29", "23373844455138", 56_000_000),
    # ── 2025 Q2 ──────────────────────────────
    ("2025-04-02", "6182226354640",  58_000_000),
    ("2025-04-05", "711162334479",    5_000_000),
    ("2025-04-09", "3172435464838",   7_000_000),
    ("2025-04-12", "14202330404322",  9_000_000),
    ("2025-04-16", "16202937485317", 11_000_000),
    ("2025-04-19", "5212636415020",  13_000_000),
    ("2025-04-23", "8132229354524",  15_000_000),
    ("2025-04-26", "3162439495613",  17_000_000),
    ("2025-04-30", "912273644528",   19_000_000),
    ("2025-05-03", "6151723374119",  21_000_000),
    ("2025-05-07", "14212834455222", 23_000_000),
    ("2025-05-10", "31930364148",    25_000_000),   # partial string — 6 balls, no bonus
    ("2025-05-14", "5916223551",      5_000_000),
    ("2025-05-17", "813202636452",    7_000_000),
    ("2025-05-21", "16233140444926",  9_000_000),
    ("2025-05-24", "3121826333910",  11_000_000),
    ("2025-05-28", "5182939465134",  13_000_000),
    ("2025-05-31", "6111719283840",  15_000_000),
    ("2025-06-04", "2142027384226",  17_000_000),
    ("2025-06-07", "17222930405516", 19_000_000),
    ("2025-06-11", "5121628395238",  21_000_000),
    ("2025-06-14", "7142230364841",  23_000_000),
    ("2025-06-18", "19253137485321", 25_000_000),
    ("2025-06-21", "8152228344912",  27_000_000),
    ("2025-06-25", "113182047502",    9_000_000),
    ("2025-06-28", "11318204750",     5_000_000),
    # ── 2025 Q3 ──────────────────────────────
    ("2025-07-02", "8112635444541",   2_600_000),
    ("2025-07-05", "8142930495223",   5_800_000),
    ("2025-07-09", "181213313549",    8_400_000),
    ("2025-07-12", "5671530342",      2_500_000),
    ("2025-07-16", "8102744454826",   5_200_000),
    ("2025-07-19", "281113364630",    8_000_000),
    ("2025-07-23", "58151740524",    10_400_000),
    ("2025-07-26", "12162022275221", 13_700_000),
    ("2025-07-30", "6272934475015",  16_600_000),
    ("2025-08-02", "6162530505135",  20_200_000),
    ("2025-08-06", "351826314922",   23_200_000),
    ("2025-08-09", "4153839415133",  26_800_000),
    ("2025-08-13", "241934385049",   29_600_000),
    ("2025-08-16", "2151722235019",  33_000_000),
    ("2025-08-20", "2141619414345",  35_800_000),
    ("2025-08-23", "10142231324939", 38_600_000),
    ("2025-08-27", "3111728445248",  41_500_000),
    ("2025-08-30", "8252936465120",   3_100_000),
    ("2025-09-03", "17252630444838",  5_700_000),
    ("2025-09-06", "3122839415042",   8_600_000),
    ("2025-09-10", "1926283537463",  10_800_000),
    ("2025-09-13", "12202122283342", 13_300_000),
    ("2025-09-17", "12182327385248", 15_500_000),
    ("2025-09-20", "451421345246",   18_100_000),
    ("2025-09-24", "16233242495855",  3_000_000),
    ("2025-09-27", "712143237525",    5_000_000),
    # ── 2025 Q4 ──────────────────────────────
    ("2025-10-01", "5121420283016",   7_000_000),
    ("2025-10-04", "483641435745",    9_700_000),
    ("2025-10-08", "7112935465626",   3_000_000),
    ("2025-10-11", "23242733365818",  5_000_000),
    ("2025-10-15", "16172027495157",  7_000_000),
    ("2025-10-18", "5273337415818",   9_000_000),
    ("2025-10-22", "8173140445348",  11_000_000),
    ("2025-10-25", "7273945485636",  13_000_000),
    ("2025-10-29", "210224345536",   16_000_000),
    ("2025-11-01", "1122124495644",  19_000_000),
    ("2025-11-05", "9133351555819",  22_000_000),
    ("2025-11-08", "910193852557",   24_000_000),
    ("2025-11-12", "9162039445647",  27_000_000),
    ("2025-11-15", "13313343465320", 29_000_000),
    ("2025-11-19", "14192126565837", 31_000_000),
    ("2025-11-22", "45615395028",    34_000_000),
    ("2025-11-26", "482532333622",   36_000_000),
    ("2025-11-29", "8182246545851",  40_000_000),
    ("2025-12-03", "182932425345",   42_000_000),
    ("2025-12-06", "461315293520",   45_000_000),
    ("2025-12-10", "10131422324857", 47_000_000),
    ("2025-12-13", "918305354588",   50_000_000),
    ("2025-12-17", "161226405438",   52_000_000),
    ("2025-12-20", "5404749535429",  55_000_000),
    ("2025-12-24", "7122039435634",  58_000_000),
    ("2025-12-27", "8112432434541",  61_000_000),
    ("2025-12-31", "451016224525",   65_200_000),
    # ── 2026 Q1 ──────────────────────────────
    ("2026-01-03", "1243334455537",  65_000_000),
    ("2026-01-07", "46294449572",     5_000_000),
    ("2026-01-10", "7182936515840",   7_000_000),
    ("2026-01-14", "16343643565755",  9_000_000),
    ("2026-01-17", "24323849555851", 11_000_000),
    ("2026-01-21", "918323554562",   13_000_000),
    ("2026-01-24", "7232837505819",  15_000_000),
    ("2026-01-28", "9181936374950",  18_000_000),
    ("2026-01-31", "15323639404828", 21_000_000),
    ("2026-02-04", "3172026515322",  24_000_000),
    ("2026-02-07", "131221485130",   26_000_000),
    ("2026-02-11", "1416222429353",  29_000_000),
    ("2026-02-14", "6101832374653",  31_000_000),
    ("2026-02-18", "6132236505628",  34_000_000),
    ("2026-02-21", "28394345556",    36_000_000),
    ("2026-02-25", "7111232385520",  39_000_000),
    ("2026-02-28", "27153338485",    42_000_000),
    ("2026-03-04", "1101117375725",  45_000_000),
    ("2026-03-07", "4131420224729",  48_000_000),
    ("2026-03-11", "254954565846",   50_000_000),
    ("2026-03-14", "12223032425857", 52_000_000),
    ("2026-03-18", "424264546495",   55_000_000),
    ("2026-03-21", "37162242539",    58_000_000),
    ("2026-03-25", "1121928315238",  61_000_000),
    ("2026-03-28", "6122640415517",  65_000_000),
    # ── 2026 Q2 (through May 2026) ───────────
    ("2026-04-01", "14182729525610", 68_000_000),
    ("2026-04-04", "1113153039488",  71_000_000),
    ("2026-04-08", "2234043485355",  74_000_000),
    ("2026-04-11", "1541434557581",  77_000_000),
    ("2026-04-15", "121022275455",   80_000_000),
    ("2026-04-18", "2325314852538",  83_000_000),
    ("2026-04-22", "1012232627375",  86_000_000),
    ("2026-04-25", "9222630505442",  90_000_000),
    ("2026-04-30", "391532364940",   93_000_000),
    ("2026-05-02", "7283240444937",  96_000_000),
    ("2026-05-06", "682340424410",  100_644_721),  # jackpot WON — R100.6M
    ("2026-05-09", "182124455256",    3_000_000),
    ("2026-05-13", "1223374051584",   5_000_000),
    ("2026-05-16", "34404245565852",  6_500_000),
    ("2026-05-20", "14121324581",     8_500_000),
    ("2026-05-23", "33394547495334", 10_500_000),
    ("2026-05-30", "21353946515624", 15_500_000),
]


def build_new_records(raw: list, last_draw_num: int) -> pd.DataFrame:
    """
    Convert raw (date, string, jackpot) tuples into structured draw records
    matching the original dataset schema.

    For each entry:
      - Decode the ball string using parse_result_string()
      - Sort the 6 main balls ascending
      - Extract the bonus ball (7th value)
      - Assign a sequential draw number
      - Fill archive-only columns (prize divisions etc.) with 0 / empty

    Args:
        raw           : list of (date_str, result_str, jackpot_int) tuples
        last_draw_num : highest drawNumber in the existing dataset

    Returns:
        DataFrame of new draw records ready for concatenation.
    """
    records = []
    draw_num = last_draw_num + 1

    for date_str, result_str, jackpot in raw:
        # try 7 values (6 balls + bonus); fall back to 6 if string is partial
        balls = parse_result_string(result_str, n=7, max_val=58)
        if not balls or len(balls) != 7:
            balls = parse_result_string(result_str, n=6, max_val=58)
            balls = (balls or []) + [0]   # 0 = bonus unknown

        if len(balls) < 7:
            print(f"  ⚠ SKIP {date_str}: could not parse '{result_str}'")
            continue

        main   = sorted(balls[:6])
        bonus  = balls[6]

        records.append({
            'drawNumber'      : draw_num,
            'drawDate'        : date_str,
            'nextDrawDate'    : '',
            'ball1'           : main[0],
            'ball2'           : main[1],
            'ball3'           : main[2],
            'ball4'           : main[3],
            'ball5'           : main[4],
            'ball6'           : main[5],
            'bonusBall'       : bonus,
            # prize division columns — not available for new draws
            'div1Winners'     : 0, 'div1Payout' : 0,
            'div2Winners'     : 0, 'div2Payout' : 0,
            'div3Winners'     : 0, 'div3Payout' : 0,
            'div4Winners'     : 0, 'div4Payout' : 0,
            'div5Winners'     : 0, 'div5Payout' : 0,
            'div6Winners'     : 0, 'div6Payout' : 0,
            'div7Winners'     : 0, 'div7Payout' : 0,
            'div8Winners'     : 0, 'div8Payout' : 0,
            'rolloverAmount'  : 0,
            'rolloverNumber'  : 0,
            'totalPrizePool'  : 0,
            'totalSales'      : 0,
            'estimatedJackpot': jackpot,
            'guaranteedJackpot': 0,
            'drawMachine'     : '',
            'ballSet'         : '',
            'status'          : 'Results',
            # provincial winner columns
            'gpwinners'  : 0, 'wcwinners'  : 0, 'ncwinners'  : 0,
            'ecwinners'  : 0, 'mpwinners'  : 0, 'lpwinners'  : 0,
            'fswinners'  : 0, 'kznwinners' : 0, 'nwwinners'  : 0,
            'winners'    : 0,
            'millionairs': 0,
        })
        draw_num += 1

    return pd.DataFrame(records)


# ─────────────────────────────────────────────
# 4. MERGE & CLEAN
# ─────────────────────────────────────────────

def merge_and_clean(original: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """
    Concatenate original and new draws, sort chronologically,
    re-index draw numbers sequentially, and validate ball ranges.

    Validation rules:
      - All main balls must be in [1, 52] (original pool; new draws may use up to 58)
      - No duplicate balls within a single draw
      - drawDate must be a valid date
      - drawNumber must be unique

    Args:
        original : original DataFrame (985 draws)
        new      : new DataFrame (146 draws)

    Returns:
        Cleaned, combined DataFrame.
    """
    combined = pd.concat([original, new], ignore_index=True)
    combined['drawDate'] = pd.to_datetime(combined['drawDate'])
    combined = combined.sort_values('drawDate').reset_index(drop=True)

    # re-assign sequential draw numbers after sort
    combined['drawNumber'] = range(1, len(combined) + 1)

    # validate: flag draws with any ball out of range 1–58
    ball_cols = ['ball1','ball2','ball3','ball4','ball5','ball6']
    invalid = combined[combined[ball_cols].apply(
        lambda row: any(v < 1 or v > 58 for v in row), axis=1
    )]
    if not invalid.empty:
        print(f"  ⚠ {len(invalid)} draws with out-of-range balls:")
        print(invalid[['drawNumber','drawDate'] + ball_cols])

    # validate: flag draws with duplicate balls
    dupes = combined[combined[ball_cols].apply(
        lambda row: len(set(row)) < 6, axis=1
    )]
    if not dupes.empty:
        print(f"  ⚠ {len(dupes)} draws with duplicate balls:")
        print(dupes[['drawNumber','drawDate'] + ball_cols])

    print(f"\nCombined dataset: {len(combined):,} draws")
    print(f"Date range      : {combined['drawDate'].min().date()} → {combined['drawDate'].max().date()}")
    return combined


# ─────────────────────────────────────────────
# 5. STATISTICAL FEATURE ENGINEERING
# ─────────────────────────────────────────────

BALL_COLS = ['ball1','ball2','ball3','ball4','ball5','ball6']

def compute_frequency(df: pd.DataFrame) -> dict:
    """
    Count how many times each ball (1–52) has appeared across all draws.
    Returns a dict {ball_number: count}.
    """
    all_balls = df[BALL_COLS].values.flatten()
    freq = Counter(int(b) for b in all_balls if 1 <= b <= 52)
    return dict(sorted(freq.items()))


def compute_hot(df: pd.DataFrame, window: int = 50) -> list:
    """
    Find the most frequently drawn balls in the last `window` draws.
    Returns a list of ball numbers sorted by recent frequency descending.
    """
    recent = df.tail(window)
    recent_balls = recent[BALL_COLS].values.flatten()
    hot_counter = Counter(int(b) for b in recent_balls if 1 <= b <= 52)
    return [n for n, _ in hot_counter.most_common()]


def compute_overdue(df: pd.DataFrame) -> list:
    """
    For each ball, find the index of its most recent appearance.
    Balls not seen recently have a higher 'overdue' score.

    Returns a list of ball numbers sorted by overdue score descending
    (most overdue first).
    """
    last_seen = {}
    for idx, row in df.iterrows():
        for col in BALL_COLS:
            v = int(row[col])
            if 1 <= v <= 52:
                last_seen[v] = idx

    total = len(df)
    overdue_scores = {
        n: total - last_seen.get(n, -1)
        for n in range(1, 53)
    }
    return [n for n, _ in sorted(overdue_scores.items(), key=lambda x: -x[1])]


def compute_top_pairs(df: pd.DataFrame, top_n: int = 20) -> list:
    """
    Count how often each pair of balls has appeared in the same draw.
    Returns the top_n most frequent pairs as [(ball_a, ball_b), ...].
    """
    pair_counter = Counter()
    for _, row in df.iterrows():
        balls = sorted(int(row[c]) for c in BALL_COLS if 1 <= int(row[c]) <= 52)
        for pair in combinations(balls, 2):
            pair_counter[pair] += 1
    return [pair for pair, _ in pair_counter.most_common(top_n)]


def compute_bonus_frequency(df: pd.DataFrame) -> dict:
    """
    Count frequency of each bonus ball value across all draws.
    Returns a dict {ball_number: count}.
    """
    bonus_vals = df['bonusBall'].values
    freq = Counter(int(b) for b in bonus_vals if 1 <= b <= 52)
    return dict(sorted(freq.items()))


def print_model_summary(df: pd.DataFrame) -> None:
    """
    Print a full statistical summary used by the dashboard's prediction model.
    """
    freq      = compute_frequency(df)
    hot       = compute_hot(df, window=50)
    overdue   = compute_overdue(df)
    top_pairs = compute_top_pairs(df, top_n=10)
    bonus_freq= compute_bonus_frequency(df)

    print("\n── FREQUENCY (top 10) ──────────────────────")
    top_freq = sorted(freq.items(), key=lambda x: -x[1])[:10]
    for ball, count in top_freq:
        print(f"  Ball {ball:>2}: {count} draws")

    print("\n── HOT (last 50 draws, top 10) ─────────────")
    print(" ", hot[:10])

    print("\n── OVERDUE (top 10) ─────────────────────────")
    print(" ", overdue[:10])

    print("\n── TOP PAIRS (top 10) ───────────────────────")
    for p in top_pairs:
        print(f"  {p}")

    print("\n── BONUS FREQUENCY (top 10) ─────────────────")
    top_bonus = sorted(bonus_freq.items(), key=lambda x: -x[1])[:10]
    for ball, count in top_bonus:
        print(f"  Ball {ball:>2}: {count} draws")


# ─────────────────────────────────────────────
# 6. EXPORT
# ─────────────────────────────────────────────

def save(df: pd.DataFrame, path: str) -> None:
    """
    Save the final enhanced dataset to CSV.
    Index is excluded — drawNumber is the primary key.
    """
    df.to_csv(path, index=False)
    print(f"\n✅ Saved {len(df):,} draws → {path}")


# ─────────────────────────────────────────────
# 7. MAIN
# ─────────────────────────────────────────────

if __name__ == '__main__':

    INPUT_PATH  = 'lotteries.csv'           # original raw file
    OUTPUT_PATH = 'lotteries_enhanced.csv'  # final enhanced file

    print("=" * 52)
    print("  SA Lotto Predictor — Data Pipeline")
    print("  Erskine Brister Shikonele · CSE")
    print("=" * 52, "\n")

    # Step 1 — load
    df_original = load_raw(INPUT_PATH)

    # Step 2 — build new records
    print("Building new draw records...")
    df_new = build_new_records(NEW_DRAWS_RAW, last_draw_num=df_original['drawNumber'].max())
    print(f"  {len(df_new)} new records built\n")

    # Step 3 — merge & clean
    print("Merging and validating...")
    df_final = merge_and_clean(df_original, df_new)

    # Step 4 — statistical model summary
    print_model_summary(df_final)

    # Step 5 — export
    save(df_final, OUTPUT_PATH)
