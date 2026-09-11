#!/usr/bin/env python3
"""Independently join every candidate back to its two source records."""
import argparse
import json
from pathlib import Path

import stockdb_offline_export as e
import repair_stockdb_preclose as r


def verify(root):
    report = json.loads((root / 'preclose_full_v1/validation.json').read_text())
    target = root / 'preclose_independent_verification.json'
    if target.exists():
        raise FileExistsError('immutable verification already exists')
    if e.sha256_file(Path(report['output']['path'])) != report['output']['sha256']:
        raise ValueError('candidate output changed')
    for path, expected in report['source_hashes'].items():
        if e.sha256_file(Path(path)) != expected:
            raise ValueError('source changed: ' + path)
    c = r.connect()
    r.prepare(c, [])
    # DuckDB DDL cannot bind table-function parameters; quote this verified path.
    candidate_path = report['output']['path'].replace("'", "''")
    c.execute(f"CREATE VIEW candidate AS SELECT * FROM read_parquet('{candidate_path}')")
    expected = report['candidate_rows']
    tests = {}
    for label, sql in {
        'original_record_and_price': """SELECT count(*),count_if(
          p.original_pre_close=d.pre_close AND p.close=d.close AND p.pct_chg=d.pct_chg
          AND p.code=d.code AND p.date=d.date
          AND d.low>0 AND d.low<=d.open AND d.low<=d.close AND d.high>=d.open AND d.high>=d.close)
          FROM candidate p LEFT JOIN input_daily d ON p.source_db=d.source_db
          AND p.logical_key=d.logical_key AND p.source_file=d.source_file AND p.source_sequence=d.source_sequence""",
        'previous_record_and_price': """SELECT count(*),count_if(
          p.candidate_pre_close=d.close AND p.prev_date=d.date AND p.code=d.code
          AND d.low>0 AND d.low<=d.open AND d.low<=d.close AND d.high>=d.open AND d.high>=d.close)
          FROM candidate p LEFT JOIN input_daily d ON p.prev_source_db=d.source_db
          AND p.prev_logical_key=d.logical_key AND p.prev_source_file=d.source_file
          AND p.prev_source_sequence=d.source_sequence""",
        'calendar_and_recomputed_return': """WITH cal AS (
          SELECT date,lag(date) OVER(ORDER BY date) previous_date FROM input_calendar)
          SELECT count(*),count_if(p.prev_date=cal.previous_date
          AND abs((p.close/p.candidate_pre_close-1)*100-p.pct_chg)<=0.005
          AND abs((p.close/p.original_pre_close-1)*100-p.pct_chg)>0.2)
          FROM candidate p LEFT JOIN cal ON p.date=cal.date""",
    }.items():
        result = c.execute(sql).fetchone()
        if result != (expected, expected):
            raise ValueError(f'{label} mismatch: {result}')
        tests[label] = {'rows': result[0], 'passed': result[1]}
        print(label, result, flush=True)
    event_leaks = c.execute('SELECT count(*) FROM candidate p SEMI JOIN input_events v USING(code,date)').fetchone()[0]
    if event_leaks:
        raise ValueError('known event candidates leaked')
    result = {'status': 'all_candidates_reconciled_with_both_source_records', 'candidate_rows': expected,
              'tests': tests, 'known_event_leaks': event_leaks,
              'candidate_sha256': report['output']['sha256'],
              'verifier_sha256': e.sha256_file(Path(__file__)),
              'meaning': 'verified derivation/lineage, not independent market-price or backtest acceptance'}
    e.atomic_json(target, result)
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    args=p.parse_args()
    print(json.dumps(verify(args.root),ensure_ascii=False,indent=2))
