"""Fetch from SEC EDGAR: the filing text (for retrieval) and the structured
financial data (for analysis, via XBRL company facts). Standard library +
requests + BeautifulSoup only."""
from datetime import date

import requests
from bs4 import BeautifulSoup

from .. import config

_HEADERS = {"User-Agent": config.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# XBRL us-gaap concepts we care about, each with fallback tags (companies tag
# the same line differently), as (display_name, [candidate_tags]).
INCOME_STATEMENT_CONCEPTS = [
    ("Revenues", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]),
    ("CostOfRevenue", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]),
    ("GrossProfit", ["GrossProfit"]),
    ("OperatingIncomeLoss", ["OperatingIncomeLoss"]),
    ("NetIncomeLoss", ["NetIncomeLoss", "ProfitLoss"]),
]
BALANCE_SHEET_CONCEPTS = [
    ("Assets", ["Assets"]),
    ("AssetsCurrent", ["AssetsCurrent"]),
    ("Liabilities", ["Liabilities"]),
    ("LiabilitiesCurrent", ["LiabilitiesCurrent"]),
    ("StockholdersEquity", ["StockholdersEquity"]),
    ("CashAndCashEquivalentsAtCarryingValue", ["CashAndCashEquivalentsAtCarryingValue"]),
]


def _http_get(url: str) -> requests.Response:
    response = requests.get(url, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    return response


def resolve_cik(ticker: str):
    companies = _http_get(_TICKERS_URL).json()
    wanted = ticker.upper().strip()
    for company in companies.values():
        if company["ticker"].upper() == wanted:
            return f"{int(company['cik_str']):010d}", company["title"]
    raise ValueError(f"ticker '{ticker}' not found in SEC ticker list")


def latest_filing(cik: str, form: str):
    submissions = _http_get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    recent = submissions["filings"]["recent"]
    report_dates = recent.get("reportDate", [""] * len(recent["form"]))
    for index, filed_form in enumerate(recent["form"]):
        if filed_form == form:
            return {
                "accession": recent["accessionNumber"][index],
                "primary_doc": recent["primaryDocument"][index],
                "period": report_dates[index],
                "form": filed_form,
            }
    raise ValueError(f"no {form} found for CIK {cik}")


def fetch_filing_text(cik: str, accession: str, primary_doc: str) -> str:
    accession_plain = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_plain}/{primary_doc}"
    html = _http_get(url).text
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n")


def _values_by_year(company_facts, candidate_tags):
    """Return {fiscal_year -> value}, keyed by each value's own period end (not
    the filing's `fy`, which is unreliable — a 10-K reports several years). Income
    statement concepts (duration) are limited to ~full-year periods; balance sheet
    concepts (instant) take the year-end value. Candidate tags are merged, and the
    latest restatement wins."""
    by_year = {}  # year -> (period_end, filed_date, value)
    for tag in candidate_tags:
        concept = company_facts.get("us-gaap", {}).get(tag)
        if concept is None:
            continue
        for entry in concept.get("units", {}).get("USD", []):
            if not str(entry.get("form", "")).startswith("10-K"):
                continue
            period_end = entry.get("end")
            if not period_end:
                continue
            period_start = entry.get("start")
            if period_start:  # duration concept -> keep only ~full-year periods
                try:
                    span_days = (date.fromisoformat(period_end) - date.fromisoformat(period_start)).days
                except ValueError:
                    continue
                if not (330 <= span_days <= 400):
                    continue
            year = int(period_end[:4])
            filed_date = entry.get("filed", "")
            current = by_year.get(year)
            if current is None or (period_end, filed_date) > (current[0], current[1]):
                by_year[year] = (period_end, filed_date, entry.get("val"))
    return {year: record[2] for year, record in by_year.items()}


def _build_dataset(company_facts, concept_specs, label):
    series_by_name = {}
    for display_name, candidate_tags in concept_specs:
        series_by_name[display_name] = _values_by_year(company_facts, candidate_tags)

    all_years = set()
    for series in series_by_name.values():
        for year in series:
            all_years.add(year)
    years = sorted(all_years)[-4:]  # last four fiscal years
    if not years:
        return None

    columns = ["line_item"]
    for year in years:
        columns.append(f"FY{year}")

    rows = []
    for display_name, _tags in concept_specs:
        series = series_by_name[display_name]
        if not series:
            continue
        row = [display_name]
        for year in years:
            row.append(series.get(year))
        rows.append(row)

    if not rows:
        return None
    return {"label": label, "columns": columns, "rows": rows}


def fetch_financials(cik: str) -> dict:
    facts = _http_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json").json().get("facts", {})
    datasets = {}
    income_statement = _build_dataset(facts, INCOME_STATEMENT_CONCEPTS, "Item 8 · Income Statement (XBRL)")
    balance_sheet = _build_dataset(facts, BALANCE_SHEET_CONCEPTS, "Item 8 · Balance Sheet (XBRL)")
    if income_statement:
        datasets["income_statement"] = income_statement
    if balance_sheet:
        datasets["balance_sheet"] = balance_sheet
    return datasets
