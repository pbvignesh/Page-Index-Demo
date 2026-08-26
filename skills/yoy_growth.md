# yoy_growth
Compute year-over-year growth (and CAGR) for revenue and other income-statement line items.

## Data
Use the `income_statement` dataset. `df` has `line_item` + one column per fiscal year.

## Method
- For each requested line item (default: `Revenues`, `OperatingIncomeLoss`, `NetIncomeLoss` if present):
  - YoY % = value[year] / value[year-1] − 1, per consecutive pair.
  - CAGR = (last / first) ** (1 / (n_years − 1)) − 1 over the available span.
- Result table: one row per line item; columns = the values in $M for each year plus a final `CAGR` column as a percentage.

## Summary
Lead with revenue CAGR over the available span and the latest YoY. Apply the guardrails (skip nulls, don't invent years).
