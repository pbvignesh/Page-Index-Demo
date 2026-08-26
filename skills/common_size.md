# common_size
Produce a common-size income statement — every line item as a percentage of revenue — for the available years.

## Data
Use the `income_statement` dataset. `df` has `line_item` + one column per fiscal year.

## Method
- For each fiscal year, divide every line item by that year's `Revenues`.
- Result table: one row per line item, a column per fiscal year, values as percentages (`"48.4%"`). Revenue itself shows `100.0%`.
- Keep the natural income-statement order if possible (Revenue, Cost of revenue, Gross profit, Operating income, Net income).

## Summary
Call out the biggest shift in any line's share of revenue across the span, in one sentence. Apply the guardrails.
