"""Fetch from SEC EDGAR: the filing text (for retrieval) and the structured
financial data (for analysis, via XBRL companyfacts). Only the standard library
+ requests + BeautifulSoup — no scraping heroics."""
from datetime import date

import requests
from bs4 import BeautifulSoup

from . import config

_H = {"User-Agent": config.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# XBRL us-gaap concepts we care about, with fallbacks (companies tag differently).
_INCOME = [
    ("Revenues", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]),
    ("CostOfRevenue", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]),
    ("GrossProfit", ["GrossProfit"]),
    ("OperatingIncomeLoss", ["OperatingIncomeLoss"]),
    ("NetIncomeLoss", ["NetIncomeLoss", "ProfitLoss"]),
]
_BALANCE = [
    ("Assets", ["Assets"]),
    ("AssetsCurrent", ["AssetsCurrent"]),
    ("Liabilities", ["Liabilities"]),
    ("LiabilitiesCurrent", ["LiabilitiesCurrent"]),
    ("StockholdersEquity", ["StockholdersEquity"]),
    ("CashAndCashEquivalentsAtCarryingValue", ["CashAndCashEquivalentsAtCarryingValue"]),
]


def _get(url):
    r = requests.get(url, headers=_H, timeout=30)
    r.raise_for_status()
    return r


def resolve_cik(ticker: str):
    data = _get(_TICKERS_URL).json()
    t = ticker.upper().strip()
    for row in data.values():
        if row["ticker"].upper() == t:
            return f"{int(row['cik_str']):010d}", row["title"]
    raise ValueError(f"ticker '{ticker}' not found in SEC ticker list")


def latest_filing(cik: str, form: str):
    data = _get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    r = data["filings"]["recent"]
    for i, f in enumerate(r["form"]):
        if f == form:
            return {
                "accession": r["accessionNumber"][i],
                "primary_doc": r["primaryDocument"][i],
                "period": r.get("reportDate", [""] * len(r["form"]))[i],
                "form": f,
            }
    raise ValueError(f"no {form} found for CIK {cik}")


def fetch_filing_text(cik: str, accession: str, primary_doc: str) -> str:
    acc = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{primary_doc}"
    html = _get(url).text
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n")


def _concept_by_year(facts, tags):
    """Return {fiscal_year:int -> value}, keyed by the value's own period end
    (not the filing's `fy`, which is unreliable). Duration concepts (income
    statement) are restricted to annual spans; instant concepts (balance sheet)
    take the year-end value. Candidate tags are merged so an older tag can fill
    years a newer one doesn't cover; the latest-filed restatement wins."""
    best = {}  # year -> (end, filed, value)
    for tag in tags:
        node = facts.get("us-gaap", {}).get(tag)
        if not node:
            continue
        for e in node.get("units", {}).get("USD", []):
            if not str(e.get("form", "")).startswith("10-K"):
                continue
            end = e.get("end")
            if not end:
                continue
            start = e.get("start")
            if start:  # duration -> keep only ~full-year periods
                try:
                    if not (330 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 400):
                        continue
                except ValueError:
                    continue
            year, filed = int(end[:4]), e.get("filed", "")
            cur = best.get(year)
            if cur is None or (end, filed) > (cur[0], cur[1]):
                best[year] = (end, filed, e.get("val"))
    return {y: v[2] for y, v in best.items()}


def _build_dataset(facts, spec, label):
    series = {name: _concept_by_year(facts, tags) for name, tags in spec}
    years = sorted({y for s in series.values() for y in s})[-4:]  # last 4 fiscal years
    if not years:
        return None
    columns = ["line_item"] + [f"FY{y}" for y in years]
    rows = []
    for name, _ in spec:
        s = series[name]
        if not s:
            continue
        rows.append([name] + [s.get(y) for y in years])
    if not rows:
        return None
    return {"label": label, "columns": columns, "rows": rows}


def fetch_financials(cik: str) -> dict:
    facts = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json").json().get("facts", {})
    out = {}
    inc = _build_dataset(facts, _INCOME, "Item 8 · Income Statement (XBRL)")
    bal = _build_dataset(facts, _BALANCE, "Item 8 · Balance Sheet (XBRL)")
    if inc:
        out["income_statement"] = inc
    if bal:
        out["balance_sheet"] = bal
    return out
