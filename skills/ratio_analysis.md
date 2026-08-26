# ratio_analysis
Compute core balance-sheet health ratios across the available years.

## Data
Use the `balance_sheet` dataset. `df` has `line_item` + one column per fiscal year.
Relevant items (use whichever are present): `AssetsCurrent`, `LiabilitiesCurrent`, `Assets`, `Liabilities`, `StockholdersEquity`, `CashAndCashEquivalentsAtCarryingValue`.

## Method
- **Current ratio** = AssetsCurrent / LiabilitiesCurrent.
- **Debt-to-equity** = Liabilities / StockholdersEquity.
- **Equity ratio** = StockholdersEquity / Assets.
- Compute each per year where the inputs are present; round ratios to 2 decimals.
- Result table: one row per ratio, a column per fiscal year.

## Summary
Note whether liquidity/leverage improved or deteriorated over the span, in one sentence. Apply the guardrails.
