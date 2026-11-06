"""Run with python -m unittest -v. All tests are local; no model calls."""
import argparse
import asyncio
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app
from reference import build_reference, read_sales

TEST_ROOT = app.ROOT / 'outputs' / 'test_work'
TEST_ROOT.mkdir(parents=True, exist_ok=True)


class DataTests(unittest.TestCase):
    def test_bundled_calculations_and_tie_rules(self):
        report = build_reference(app.ROOT / 'data')
        sales = report['sales']
        self.assertEqual((sales['input_records'], sales['valid_records'], sales['excluded_records']), (7,4,3))
        self.assertEqual(sales['total_revenue'], '1100.00')
        self.assertEqual(sales['mean_revenue_per_valid_transaction'], '275.00')
        self.assertEqual(sales['minimum_transaction_revenue'], '100.00')
        self.assertEqual(sales['maximum_transaction_revenue'], '500.00')
        self.assertEqual(sales['top_two_exact'], ['Monitor', 'Keyboard'])
        self.assertEqual(sales['top_two_including_ties'], ['Monitor', 'Keyboard', 'Mouse'])
        self.assertEqual([c['share_percent'] for c in sales['categories']], ['54.5', '45.5'])
        self.assertEqual([c['percent_change'] for c in report['monthly_changes']], ['50.0', '-20.0'])

    def test_null_and_absent_are_distinct(self):
        orders = build_reference(app.ROOT / 'data')['orders']
        self.assertEqual([r['total_state'] for r in orders], ['value', 'null', 'missing'])

    def test_csv_quotes_and_exclusions(self):
        rows, issues, count = read_sales(app.ROOT / 'data' / 'sales.csv')
        self.assertEqual(rows[0]['customer'], 'Acme, Inc.')
        self.assertEqual(issues, [{'record':5,'reason':'missing revenue'},
                                  {'record':6,'reason':'invalid revenue'},
                                  {'record':7,'reason':'duplicate transaction_id'}])

    def test_nonfinite_negative_malformed_and_duplicate_values(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            path = Path(temp) / 'sales.csv'
            path.write_text('transaction_id,customer,product,category,revenue\n'
                            'a,A,P,C,NaN\nb,B,P,C,Infinity\nc,C,P,C,-1\n'
                            'd,D,P,C\ne,E,P,C,0.10\nf,F,P,C,0.20\na,A,P,C,4\n')
            rows, issues, count = read_sales(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(str(sum(row['amount'] for row in rows)), '0.30')
            self.assertEqual(len(issues), 5)
            self.assertEqual(issues[-1]['reason'], 'duplicate transaction_id')

    def test_empty_sales_has_no_mean_and_no_ranking(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            data = Path(temp)
            shutil.copytree(app.ROOT / 'data', data, dirs_exist_ok=True)
            (data / 'sales.csv').write_text('transaction_id,customer,product,category,revenue\n')
            sales = build_reference(data)['sales']
            self.assertEqual(sales['total_revenue'], '0.00')
            self.assertIsNone(sales['mean_revenue_per_valid_transaction'])
            self.assertEqual(sales['top_two_including_ties'], [])

    def test_zero_monthly_baseline(self):
        import shutil
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
            data = Path(temp)
            shutil.copytree(app.ROOT / 'data', data, dirs_exist_ok=True)
            (data / 'monthly_revenue.csv').write_text('month,revenue\n2026-01,0\n2026-02,20\n')
            self.assertIsNone(build_reference(data)['monthly_changes'][0]['percent_change'])

    def test_offline_and_dry_run(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp, redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(['--offline', '--output-dir', temp]), 0)
            self.assertTrue((Path(temp) / 'reference_report.md').exists())
            self.assertFalse((Path(temp) / 'agent_report.md').exists())
            self.assertEqual(app.main(['--dry-run']), 0)


class AgentResultTests(unittest.TestCase):
    def test_success_and_failure_handling_without_network(self):
        from claude_agent_sdk import ResultMessage
        cases = [('success',False,'# Sales report',0),
                 ('error_max_turns',True,'Partial answer',1),
                 ('success',False,'',1),
                 ('success',False,None,1)]
        for subtype,is_error,text,expected in cases:
            with self.subTest(subtype=subtype,text=text), tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp:
                message = ResultMessage(subtype=subtype,duration_ms=1,duration_api_ms=1,
                    is_error=is_error,num_turns=2,session_id='test',result=text)
                async def fake_query(*, prompt, options):
                    self.assertEqual(options.tools, ['Read'])
                    self.assertEqual(options.allowed_tools, ['Read'])
                    self.assertEqual(options.cwd, str(app.ROOT))
                    yield message
                args=argparse.Namespace(max_turns=12, model=None)
                with patch('claude_agent_sdk.query', fake_query), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(asyncio.run(app.run_agent(args,Path(temp))), expected)
                self.assertEqual((Path(temp)/'agent_report.md').exists(), expected==0)

    def test_missing_final_and_sdk_exception(self):
        async def empty_query(**kwargs):
            if False:
                yield None
        async def failed_query(**kwargs):
            raise RuntimeError('Simulated SDK connection failure')
            yield None
        for fake_query in (empty_query,failed_query):
            with tempfile.TemporaryDirectory(dir=TEST_ROOT) as temp, patch('claude_agent_sdk.query',fake_query), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                args=argparse.Namespace(max_turns=12,model=None)
                self.assertEqual(asyncio.run(app.run_agent(args,Path(temp))),1)
                self.assertTrue(json.loads((Path(temp)/'run_status.json').read_text())['is_error'])
                self.assertFalse((Path(temp)/'agent_report.md').exists())


if __name__ == '__main__':
    unittest.main()
