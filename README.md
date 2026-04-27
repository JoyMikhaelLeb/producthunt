# ProductHunt Leaderboard Scraper

A Selenium-based scraper that extracts daily ProductHunt leaderboard entries and saves company and founder data to Firestore.

## Overview

This script iterates over a date range, visiting the ProductHunt daily leaderboard for each day. For each listed product it extracts company info (name, website, social links) and founder profiles (name, title, social links), then writes the results to three Firestore collections: `ph`, `entities`, and `ppl`. It also enqueues LinkedIn enrichment tasks for discovered companies and people.

## Requirements

- Python 3.8+
- Google Chrome + matching ChromeDriver
- A Firebase service account key (`key.json` in the project root)

### Python dependencies

```
selenium
webdriver-manager
firebase-admin
```

Install with:

```bash
pip install selenium webdriver-manager firebase-admin
```

## Setup

1. Place your Firebase service account key at `key.json` in the project root.
2. Ensure ChromeDriver is installed. The script tries a hardcoded path first (`/home/joy/Downloads/chromedriver_linux64/chromedriver`) then falls back to `webdriver-manager`.
3. (Optional) Install the `create_numerical_task` module, which provides `create_about_task` and `create_ppl_task` for LinkedIn task queuing.

## Usage

Edit the date range at the bottom of the script:

```python
start_date = "2025/08/22"
end_date   = "2025/08/24"
```

To always scrape yesterday automatically, leave the default logic:

```python
yesterday_fulltime = datetime.now() - timedelta(days=1)
formatted_date = yesterday_fulltime.strftime("%Y/%-m/%d")
start_date = end_date = formatted_date
```

Then run:

```bash
python scraper.py
```

A Chrome window will open and the script will run non-headlessly by default. To enable headless mode, uncomment the `--headless` argument in `login()`.

## How it works

### 1. Date iteration — `sign_in_and_extract`

Loops over each date in the range and constructs the leaderboard URL:

```
https://www.producthunt.com/leaderboard/daily/YYYY/MM/DD/all
```

### 2. Link collection — `process_daily_leaderboard`

Scrolls the lazy-loading page, collecting product URLs via XPath (`[data-test*="post-name"] a`). Multiple fallback strategies handle anchors whose `href` attribute is not immediately available. Stops when no new links appear after `max_no_content_attempts` (default 8) consecutive scroll attempts, or when `max_links` (default 1000) is reached.

### 3. Per-product extraction — `getNormalmodel`

Navigates to `<product_url>/makers` and extracts:

| Field | Source |
|---|---|
| `name` | `<h1>` heading |
| `website` | Inline `<script>` tag containing `window[Symbol.for` |
| `company_social` | `SocialLinks` component — Twitter/X, Facebook, LinkedIn, Instagram, GitHub |
| `team` | `maker-card-*` sections — profile name, title, PH handle, social links |
| `launch_date` | Passed in from the date loop |

LinkedIn IDs are stored as handles only (e.g. `acme-corp`). All other social platforms store the full URL.

### 4. Firestore writes

| Collection | Document ID | Contents |
|---|---|---|
| `ph` | ProductHunt slug | Full company record |
| `entities` | LinkedIn company handle | Cross-reference to `ph` doc |
| `ppl` | LinkedIn person handle | Founder profile |

Documents are written with `merge=True`, so re-running the scraper on an already-processed product is a no-op (checked via `doc_ref.get().exists`).

### 5. LinkedIn task queuing

After each write, `create_about_task(linkedin_id)` and `create_ppl_task(li_id)` are called to enqueue enrichment jobs for downstream processing.

## Configuration reference

| Parameter | Location | Default | Description |
|---|---|---|---|
| `initial_wait` | `process_daily_leaderboard` | `8` s | Wait after initial page load |
| `max_no_content_attempts` | `process_daily_leaderboard` | `8` | Consecutive empty scrolls before stopping |
| `max_scroll_attempts` | `process_daily_leaderboard` | `150` | Hard cap on scroll iterations |
| `max_links` | `process_daily_leaderboard` | `1000` | Max product links per day |

## Firestore read budget

Each product already present in the `ph` collection is skipped after a single `.get()` check, keeping daily reads well within Firestore's free-tier limit of 50,000 reads/day.

## Known limitations

- Runs with a visible Chrome window by default (headless mode available but commented out).
- ChromeDriver path is hardcoded; update it or rely on `webdriver-manager` if the path differs.
- The `create_numerical_task` module is a local dependency not included in this file.
- `%-m` in `strftime` (no zero-padding) is Linux-only; use `%#m` on Windows.
