# Guardrails (always apply)

Shared rules for every analysis skill.

- **Units.** Dataset values are in **raw USD**. Convert to **$M** (divide by 1e6) for display and round to whole millions. Percentages: one decimal.
- **Periods.** Column names are fiscal years like `FY2023`. Only compare periods that are present; never invent a period. If a needed year is missing, use the years available and say so in the summary.
- **Missing data.** A cell may be `null`. Skip nulls; do not treat them as zero. If a line item the question needs is absent, set `result["summary"]` to explain what was missing rather than guessing.
- **Grounding.** Every number in the result must be derived from `df` — no external figures.

## Output contract (all skills)
Your code runs in a sandbox with a pandas DataFrame `df` already loaded. It must assign a variable **`result`**:

```python
result = {
    "columns": ["Line item", "FY2023", "FY2024", "FY2025"],   # display headers
    "rows": [["Revenue", "1,204", "1,405", "1,613"], ...],     # display strings
    "summary": "one plain-English sentence with the key finding",
}
```
Return only the code that computes `result`. Do not print anything.
