# Lesson 14 practical application: Structured Data Analyst

Build a small sales-analysis assistant with the Claude Agent SDK for Python. The assistant reads CSV and nested JSON files and returns a Markdown report. A separate Python calculation provides an answer key for checking its work.

## Purpose and lesson concepts

Imagine that a shop manager receives a transaction export and wants a reliable summary: total revenue, average transaction revenue, best-selling products by revenue, category shares, and data-quality problems. The app also demonstrates extracting nested order fields and describing a separate monthly trend.

This example covers all six lesson topics:

| Lesson topic | What students do here |
| --- | --- |
| Read CSV as structured records | Parse a quoted customer name, define one transaction per row, and flag invalid data. |
| Navigate nested JSON | Read the root `orders` array and distinguish a number, explicit `null`, and an absent key. |
| Calculate totals and averages | Define currency, exclusions, and the denominator before calculating. |
| Rank and compare | Aggregate repeated products, apply a tie rule, and calculate category shares. |
| Describe trends carefully | Calculate changes and separate observations from possible causes. |
| Run the SDK | Configure `Read`, observe tool requests, inspect `ResultMessage`, and save the final report. |

The model has the built-in `Read` tool. It has no Python execution or calculator tool. `reference.py` runs separately in the host application and is not exposed as an agent tool. Students should compare the two reports manually; the app does not automatically verify the model's prose.

## Files

```text
practical_application/
  app.py                     CLI, prompt, SDK loop, output handling
  reference.py               Independent CSV/JSON analysis using standard Python
  requirements.txt           Pinned SDK version
  Readme.md                  This guide
  test_app.py                Local calculation and mocked SDK tests
  data/
    sales.csv                Transactions, including intentional quality problems
    orders.json              Nested orders, including null and absent totals
    monthly_revenue.csv      Independent three-month series
  examples/
    reference_report.md      Saved answer key for the bundled data
    reference_report.json    Machine-readable answer key
  outputs/                   New run folders (created when running the app)
```

The three datasets are independent teaching fixtures. Their totals do not reconcile, and they should not be joined. All revenue is in USD. The customer names are fictional.

## Configure the application

Use Python 3.10 or newer. The pinned SDK version is `0.2.175`, matching the version used for local compatibility checks. Offline mode only uses the Python standard library. Live mode also needs the SDK, internet access, and Anthropic API credentials.

Open a terminal in this lesson folder and create an environment.

Windows PowerShell:

```powershell
cd practical_application
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:ANTHROPIC_API_KEY = "your-anthropic-api-key"
```

These commands call the environment's Python directly, so activation is optional. Set the key in the same terminal used to run the program. This application does not load `.env` files. The key is for Anthropic; the Inworld key used for the lesson video is unrelated.

macOS/Linux:

```bash
cd practical_application
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

Supported SDK wheels bundle the Claude Code executable. If your platform receives a source distribution without that binary, follow the [official SDK setup instructions](https://code.claude.com/docs/en/agent-sdk/quickstart) to install Claude Code. The [Python SDK repository](https://github.com/anthropics/claude-agent-sdk-python) documents package prerequisites and CLI discovery.

You may select a model with `--model MODEL_ID`, or set `CLAUDE_MODEL` in the environment. Without either, the SDK uses its default. Keep credentials in your environment, outside student source files.

## Run the application

In the commands below, `python` means the interpreter with the dependencies installed. On Windows you can replace it with `.\.venv\Scripts\python.exe`; on macOS/Linux use `.venv/bin/python`.

First explore the independent reference without making a model call:

```bash
python app.py --offline
```

Preview the exact prompt and tool options:

```bash
python app.py --dry-run
```

Generate the Claude report:

```bash
python app.py
```

Choose a model, turn limit, and output folder:

```bash
python app.py --model YOUR_MODEL_ID --max-turns 12 --output-dir outputs/my-analysis
```

Live runs use your Anthropic account and can incur API usage charges. Each default run creates a new timestamped output folder. Explicitly reusing `--output-dir` overwrites files of the same name; use a new folder for each attempt so a previous report cannot be mistaken for the current result.

The app resolves its input folder relative to `app.py`, so this also works from the lesson's parent folder:

```bash
python practical_application/app.py --offline
```

Typical live console output looks like this (tool order and report wording vary):

```text
Python reference: .../reference_report.md
[TOOL] Read: .../data/sales.csv
[TOOL] Read: .../data/orders.json
[TOOL] Read: .../data/monthly_revenue.csv
Claude report: .../agent_report.md
Compare it with reference_report.md; SDK success does not validate the arithmetic.
```

Read `agent_report.md` beside `reference_report.md`. `reference_report.json` contains precise expected values, and `run_status.json` records the SDK outcome, turns, available cost information, and tool requests. Offline mode produces only the reference files. A dry run writes nothing.

## Expected results for the supplied data

The sales CSV contains seven data records. Records 5 and 6 have missing and invalid revenue. Record 7 repeats transaction `S001`. Excluding those records leaves four valid transactions.

| Metric | Expected value |
| --- | ---: |
| Valid transactions | 4 |
| Total revenue | USD 1,100.00 |
| Mean revenue per valid transaction | USD 275.00 |
| Minimum transaction revenue | USD 100.00 |
| Maximum transaction revenue | USD 500.00 |
| Monitor grouped revenue | USD 500.00 |
| Keyboard grouped revenue | USD 300.00 |
| Mouse grouped revenue | USD 300.00 |
| Accessories share | 54.5% |
| Electronics share | 45.5% |

Exactly two top products are Monitor and Keyboard. Including ties at second place also returns Mouse. The mean uses **four valid transaction rows**, not three distinct products. This denominator differs from the product-row illustration in the slides because the practical dataset represents transactions.

Orders 101, 102, and 103 respectively have a numeric total, an explicit null total, and an absent total key. The `total_state` field in the reference preserves this distinction even though JSON output uses `null` as the placeholder for both unknown totals.

The independent monthly series rises from 100 to 150 (+50%), then falls to 120 (-20%). March remains 20% above January. These values do not establish a seasonal cycle, a promotion's effect, or profitability.

## How the application was built

### 1. Establish the record and exclusion rules

`reference.py` uses the CSV parser rather than splitting each line at commas:

```python
with path.open(encoding='utf-8-sig', newline='') as handle:
    reader = csv.DictReader(handle, strict=True)
```

The parser correctly keeps `"Acme, Inc."` in one field. The validator checks the header and field count, trims whitespace, and records problems by **data record number**, excluding the header.

Duplicate detection uses transaction IDs, not product names. Repeated products can represent different valid transactions. The first well-shaped row with an ID claims that ID even if its revenue later fails validation; later occurrences are duplicates. A malformed field-count row is excluded before ID handling. This explicit policy prevents silent changes in the denominator.

```python
if transaction_id in seen:
    reason = 'duplicate transaction_id'
else:
    seen.add(transaction_id)
```

Missing revenue is excluded and reported. Invalid strings, negative amounts, NaN, and infinity are also excluded. Negative revenue is excluded by this exercise's policy; a real system handling refunds would need a different policy.

### 2. Compute an independent answer key

Use `Decimal` for decimal arithmetic and round only when displaying a result:

```python
amount = Decimal(row['revenue'])
total = sum((row['amount'] for row in rows), Decimal(0))
mean = total / len(rows) if rows else None
```

`rounded()` applies half-up rounding to two money decimals or one percentage decimal. An empty valid dataset has no mean, minimum, or maximum. Category shares are undefined when total revenue is zero.

Group products before ranking:

```python
products[row['product']] += row['amount']
ranking = sorted(products.items(), key=lambda item: (-item[1], item[0]))
```

The negative amount sorts revenue descending; the name supplies the ascending tie rule. `top_two_exact` takes the first two entries. `top_two_including_ties` includes every product reaching the second-ranked amount.

### 3. Preserve JSON value states

```python
state = (
    'missing' if 'total' not in order
    else 'null' if order['total'] is None
    else 'value'
)
```

Looking only at `order.get('total')` would make a missing key indistinguishable from explicit null. Check key membership first. The app intentionally leaves both unknown states unknown.

### 4. Ask Claude to read and analyze

`app.py` contains the full prompt in `PROMPT`. It names all three input paths and repeats the same exclusion, aggregation, denominator, rounding, and interpretation rules used by the reference calculation.

The SDK options used in the program include:

```python
options = ClaudeAgentOptions(
    cwd=str(ROOT),
    tools=['Read'],
    allowed_tools=['Read'],
    setting_sources=[],
    mcp_servers={},
    plugins=[],
    max_turns=args.max_turns,
    model=args.model,
    system_prompt='You are a careful data analyst teaching students how to inspect structured files. '
                  'Support conclusions with the data and disclose uncertainty.',
)
```

`tools` selects the built-in tool surface; `allowed_tools` pre-approves the named tool. `cwd` sets the working directory. It is not a filesystem sandbox. `setting_sources=[]` avoids loading filesystem settings sources; the example declares no MCP servers or plugins. It is a small teaching app for the supplied local fixtures, not an isolation boundary for untrusted files. See the [official Python SDK reference](https://code.claude.com/docs/en/agent-sdk/python) for these options.

The reference is generated by the host before the model call, but its contents are not added to the prompt. The prompt asks Claude to read only the fixtures. This allows students to independently compare the agent's reasoning with deterministic calculations.

### 5. Observe the agent loop and final outcome

```python
async for message in query(prompt=PROMPT, options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                print(f'[TOOL] {block.name}')
    elif isinstance(message, ResultMessage):
        final = message
```

Claude requests file reads; the SDK executes them and returns their results to Claude. Printing a `ToolUseBlock` only observes the request. The application does not execute it a second time. The final `ResultMessage` supplies the outcome and final report text.

The app saves a completed agent report only when the final message has subtype `success`, is not an error, and contains nonblank report text. It records a failed or missing final result separately. An available partial answer becomes `incomplete_response.md`. SDK exceptions produce an error status and exit code 1. The CLI also catches local input validation failures.

An SDK success means the run completed; it does not prove that every file was fully read or that the mathematics is correct. Review tool requests, look for truncation or missing coverage in the report, and compare all important results with the reference. These logs are diagnostic evidence, not automatic completeness certification.

## Check your work

Run local tests after installing `requirements.txt`:

```bash
python -m unittest -v
```

Tests cover expected calculations, quoted commas, duplicates, missing fields, invalid and nonfinite amounts, empty datasets, zero monthly baselines, null versus missing keys, offline usage, and simulated success/error SDK results. They make no API calls. A live run is a separate integration check requiring your own Anthropic configuration.

Try these exercises:

1. Add a new valid Mouse transaction. Predict its grouped revenue and category share before running.
2. Change a missing revenue to `0`. Explain why a valid zero changes the mean's denominator.
3. Add a second transaction with an existing ID. Confirm that it is excluded.
4. Add an order with `"total": 0`. Explain its difference from null and missing.
5. Set January's monthly revenue to zero. Confirm that its percentage change is undefined.
6. Ask Claude for exactly two products, then for all products tied at second place.

## Troubleshooting and scope

| Symptom | What to check |
| --- | --- |
| `ModuleNotFoundError` | Install requirements with the same Python interpreter used to run the app. |
| Authentication failure | Set `ANTHROPIC_API_KEY` in the current terminal; check account access and billing. |
| CLI launch failure | Confirm a bundled binary exists for your installation, or install Claude Code using the official setup guide. |
| Turn-limit error | Inspect `run_status.json`; use a fresh output folder and increase `--max-turns` if appropriate. |
| Model unavailable | Use a model ID available to your account, or omit `--model`. |
| Reference validation failure | Restore the fixture headers, field counts, numeric values, and JSON object/array structure. |
| Report differs from the answer key | Compare exclusion records, denominator, product aggregation, rounding, and null handling. |

The validator is designed for small, known teaching fixtures. It is not a general schema-validation framework for arbitrary exports. Monthly dates must be unique `YYYY-MM` values; the series is sorted before comparing successive available records. If months are missing, the comparison spans a gap rather than representing a one-month change. Large files may require chunking, dedicated calculations, and explicit coverage checks beyond this lesson.
