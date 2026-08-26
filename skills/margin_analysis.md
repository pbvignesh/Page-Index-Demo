# margin_analysis
Compute gross / operating / net margins across the available fiscal years and describe the trend.

## Data
Use the `income_statement` dataset. `df` has a `line_item` column and one column per fiscal year.
Relevant line items (use whichever are present): `Revenues`, `GrossProfit`, `OperatingIncomeLoss`, `NetIncomeLoss`, `CostOfRevenue`.

## Method
- Pull each line item's row by `line_item`.
- Margin = line item / Revenues, per year. Gross margin uses GrossProfit (or Revenues − CostOfRevenue if GrossProfit absent).
- Build a result table: one row per margin available (Gross, Operating, Net), a column per fiscal year, values as `"22.6%"`.
- Also include the Revenue and Operating income rows (in $M) for context.

## Summary
State the direction and size of the operating-margin change from the first to last available year (e.g. "operating margin expanded from 18.2% to 22.6%"). Follow the guardrails.
