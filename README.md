# 🎰 SA Lotto Predictor

**Author:** Erskine Brister Shikonele — Computer Systems Engineer

A statistical analysis dashboard and smart number generator for the South African National Lottery (Lotto), built on a comprehensive historical dataset spanning over a decade of draws.

---

## 📊 Dataset

| Property | Value |
|---|---|
| File | `lotteries_enhanced.csv` |
| Total draws | 1,131 |
| Date range | 3 June 2015 – 30 May 2026 |
| Ball pool | 1–52 (6 main + 1 bonus) |
| Columns | 45 (draw number, date, balls, prize divisions, provincial winners, jackpot, sales, etc.) |

The dataset was sourced from the official SA National Lottery archive and enhanced with draws through May 2026.

---

## 🚀 Features

### Predict Tab
Six generation strategies, each weighted differently:

| Strategy | Description |
|---|---|
| 🔥 Hot Numbers | Weights balls drawn most in the last 50 draws |
| ⏰ Overdue Numbers | Favours balls absent the longest |
| 🔗 Top Pairs | Seeds picks from historically co-drawn pairs |
| ⚖️ Balanced Mix | Blends hot, overdue, and frequency signals |
| 📈 All-time Frequent | Weights by total historical frequency |
| 🎲 Smart Random | Lightly frequency-biased random selection |

- Generates 1–10 picks per session
- Each pick shows a **statistical score /100**
- Balls colour-coded 🔴 hot / 🟢 overdue
- Bonus ball selected using actual bonus-ball frequency weights
- Per-pick sum and average shown for quick review

### Statistics Tab
- Hot and overdue ball grids
- Top 10 historically co-drawn pairs
- Full distribution bar chart (colour-coded by frequency tier)

### Frequency Tab
- Ranked frequency bars for all 52 main balls
- Sort by frequency or by number
- Bonus ball top-15 frequency chart

### Recent Draws Tab
- Last 30 draws with date, balls, and jackpot
- Balls colour-coded by hot/overdue status

---

## 🗂 Repository Structure

```
sa-lotto-predictor/
├── index.html               # Main dashboard (open in any browser)
├── lotteries_enhanced.csv   # Full historical dataset
├── .gitignore
└── README.md
```

---

## 🖥 Usage

No server or build step needed. Simply open `index.html` in any modern browser:

```bash
git clone https://github.com/<your-username>/sa-lotto-predictor.git
cd sa-lotto-predictor
open index.html        # macOS
start index.html       # Windows
xdg-open index.html    # Linux
```

Or deploy to **GitHub Pages** (Settings → Pages → Deploy from branch `main`, root `/`) to get a live URL instantly.

---

## ⚠️ Disclaimer

Lottery draws are statistically independent random events. No model or statistical method can reliably predict future results. This tool is for **entertainment and data exploration only**. Please play responsibly.

---

## 📄 Licence

MIT — free to use, modify, and distribute with attribution.
