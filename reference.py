"""Independent calculations for this small teaching dataset; no AI calls."""
import csv
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


def rounded(value: Decimal, places: str = '0.01') -> str:
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def read_sales(path: Path) -> tuple[list[dict], list[dict], int]:
    """Keep the first occurrence of an ID; exclude every later occurrence."""
    valid, issues, seen = [], [], set()
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, strict=True)
        expected = ['transaction_id', 'customer', 'product', 'category', 'revenue']
        if reader.fieldnames != expected:
            raise ValueError(f'{path.name}: expected header {expected}')
        count = 0
        for count, row in enumerate(reader, 1):
            # Record numbers exclude the header (and remain valid for quoted newlines).
            reason = None
            if None in row or any(value is None for value in row.values()):
                reason = 'malformed field count'
            else:
                row = {key: value.strip() for key, value in row.items()}
                transaction_id = row['transaction_id']
                if not transaction_id:
                    reason = 'missing transaction_id'
                elif transaction_id in seen:
                    reason = 'duplicate transaction_id'
                else:
                    seen.add(transaction_id)
                    if any(not row[key] for key in expected[:-1]):
                        reason = 'missing descriptive field'
                    elif not row['revenue']:
                        reason = 'missing revenue'
                    else:
                        try:
                            amount = Decimal(row['revenue'])
                            if not amount.is_finite() or amount < 0:
                                raise InvalidOperation
                            row['amount'] = amount
                        except InvalidOperation:
                            reason = 'invalid revenue'
            if reason:
                issues.append({'record': count, 'reason': reason})
            else:
                valid.append(row)
    return valid, issues, count


def build_reference(data_dir: Path) -> dict:
    rows, issues, count = read_sales(data_dir / 'sales.csv')
    total = sum((row['amount'] for row in rows), Decimal(0))
    products, categories = defaultdict(Decimal), defaultdict(Decimal)
    for row in rows:
        products[row['product']] += row['amount']
        categories[row['category']] += row['amount']
    ranking = sorted(products.items(), key=lambda item: (-item[1], item[0]))
    sales = {
        'currency': 'USD', 'input_records': count, 'valid_records': len(rows),
        'excluded_records': len(issues), 'issues': issues,
        'total_revenue': rounded(total),
        'mean_revenue_per_valid_transaction': rounded(total / len(rows)) if rows else None,
        'minimum_transaction_revenue': rounded(min(row['amount'] for row in rows)) if rows else None,
        'maximum_transaction_revenue': rounded(max(row['amount'] for row in rows)) if rows else None,
        'products': [{'product': name, 'revenue': rounded(amount)} for name, amount in ranking],
        'top_two_exact': [name for name, _ in ranking[:2]],
        'top_two_including_ties': [name for name, amount in ranking
                                  if amount >= ranking[min(1, len(ranking)-1)][1]],
        'categories': [{'category': name, 'revenue': rounded(amount),
                        'share_percent': rounded(amount / total * 100, '0.1') if total else None}
                       for name, amount in sorted(categories.items())],
    }
    document = json.loads((data_dir / 'orders.json').read_text(encoding='utf-8-sig'))
    if not isinstance(document, dict) or not isinstance(document.get('orders'), list):
        raise ValueError('orders.json must contain a root object and an orders array')
    orders = []
    for order in document['orders']:
        if not isinstance(order, dict):
            raise ValueError('Each order must be an object')
        state = 'missing' if 'total' not in order else 'null' if order['total'] is None else 'value'
        orders.append({'id': order.get('id'), 'status': order.get('status'),
                       'total_state': state, 'total': order.get('total')})
    # This independent monthly series is not computed from sales.csv.
    with (data_dir / 'monthly_revenue.csv').open(encoding='utf-8-sig', newline='') as handle:
        monthly = list(csv.DictReader(handle, strict=True))
    months = [row['month'] for row in monthly]
    if len(set(months)) != len(months) or any(
            len(month) != 7 or month[4] != '-' or not month[:4].isdigit()
            or not month[5:].isdigit() or not 1 <= int(month[5:]) <= 12 for month in months):
        raise ValueError('Monthly dates must be unique YYYY-MM values')
    monthly.sort(key=lambda row: row['month'])
    amounts = [Decimal(row['revenue']) for row in monthly]
    if any(not amount.is_finite() or amount < 0 for amount in amounts):
        raise ValueError('Monthly revenue must be finite and nonnegative')
    changes = []
    for i in range(1, len(monthly)):
        previous, current = amounts[i-1], amounts[i]
        changes.append({'from': monthly[i-1]['month'], 'to': monthly[i]['month'],
                        'percent_change': rounded((current-previous)/previous*100, '0.1') if previous else None})
    return {'sales': sales, 'orders': orders, 'monthly_changes': changes,
            'limitations': ['The three fixtures are independent; do not join or reconcile their totals.',
                            'A missing or null value is not zero.',
                            'Three monthly points do not establish seasonality or explain causation.',
                            'Revenue does not establish profit.']}


def write_reference(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    (output_dir / 'reference_report.json').write_text(serialized + '\n', encoding='utf-8')
    sales = report['sales']
    lines = ['# Independent Python reference report', '',
             'Computed locally with Python; this is not Claude output.', '',
             f"Valid transactions: {sales['valid_records']} of {sales['input_records']}; excluded: {sales['excluded_records']}.",
             f"Total revenue: USD {sales['total_revenue']}.",
             f"Mean revenue per valid transaction: USD {sales['mean_revenue_per_valid_transaction']}.", '',
             '| Product | Revenue (USD) |', '| --- | ---: |']
    lines += [f"| {row['product']} | {row['revenue']} |" for row in sales['products']]
    lines += ['', 'The complete calculations, exclusions, JSON value states, and monthly changes follow.', '',
              '```json', serialized, '```', '']
    (output_dir / 'reference_report.md').write_text('\n'.join(lines), encoding='utf-8')
