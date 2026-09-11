#!/usr/bin/env python3
"""Conservative, traceable pre-close candidates; never overwrite native values."""
import argparse
import json
from pathlib import Path

import duckdb
import stockdb_offline_export as e

CALENDAR = Path('/Users/simon/Trading/下载数据/quant_data/2_base_sector/trading_calendar/trading_days.parquet')
SOURCE = Path('/Users/simon/Trading/下载数据/stockdb_parquet')
REPAIRS = Path('/Users/simon/Trading/下载数据/stockdb_repair_20260905')
FIELDS = 'source_db,source_file,source_sequence,logical_key,code,date,open,high,low,close,pre_close,pct_chg'

# The root reviewed and hardened the independently returned Grok prototype:
# null OHLC/calendar, previous-row duplicates and event multiplicity fail closed.
SQL = """
WITH keyed AS (
 SELECT *, count(*) OVER(PARTITION BY code,date) key_n,
   coalesce(regexp_full_match(code,'[0-9]{6}') AND logical_key='日k:'||code||':'||CAST(date AS VARCHAR),false) identity_ok,
   coalesce(open>0 AND high>0 AND low>0 AND close>0
     AND isfinite(open) AND isfinite(high) AND isfinite(low) AND isfinite(close)
     AND high>=greatest(open,close,low) AND low<=least(open,close,high),false) ohlc_ok
 FROM input_daily
), lagged AS (
 SELECT *, lag(close) OVER w prev_close, lag(date) OVER w prev_date,
   lag(logical_key) OVER w prev_logical_key, lag(source_db) OVER w prev_source_db,
   lag(source_file) OVER w prev_source_file, lag(source_sequence) OVER w prev_source_sequence,
   lag(key_n) OVER w prev_key_n, lag(ohlc_ok) OVER w prev_ohlc_ok,
   lag(identity_ok) OVER w prev_identity_ok
 FROM keyed WINDOW w AS(PARTITION BY code ORDER BY date,source_db,source_sequence)
), calendar AS (
 SELECT date, lag(date) OVER(ORDER BY date) prev_cal FROM input_calendar
), scored AS (
 SELECT d.*, c.prev_cal, (ev.code IS NOT NULL) has_event,
   CASE WHEN pre_close>0 AND isfinite(pre_close) AND isfinite(pct_chg)
     THEN abs((close/pre_close-1)*100-pct_chg) END original_return_error_pp,
   CASE WHEN prev_close>0 AND isfinite(prev_close) AND isfinite(pct_chg)
     THEN abs((close/prev_close-1)*100-pct_chg) END candidate_return_error_pp
 FROM lagged d LEFT JOIN calendar c ON c.date=d.date
 LEFT JOIN (SELECT DISTINCT code,date FROM input_events) ev ON ev.code=d.code AND ev.date=d.date
)
SELECT *, CASE
 WHEN key_n<>1 OR NOT identity_ok THEN 'identity_or_duplicate'
 WHEN NOT ohlc_ok THEN 'invalid_current_ohlc'
 WHEN pct_chg IS NULL OR NOT isfinite(pct_chg) THEN 'missing_pct_chg'
 WHEN original_return_error_pp IS NULL THEN 'original_preclose_unusable'
 WHEN original_return_error_pp<=0.2 THEN 'original_within_existing_qc_tolerance'
 WHEN prev_date IS NULL OR prev_close IS NULL THEN 'no_previous_record'
 WHEN prev_key_n IS DISTINCT FROM 1 OR NOT coalesce(prev_identity_ok,false) THEN 'ambiguous_previous_record'
 WHEN NOT coalesce(prev_ohlc_ok,false) OR prev_close<=0 OR NOT isfinite(prev_close) THEN 'invalid_previous_ohlc'
 WHEN prev_cal IS NULL THEN 'calendar_or_previous_calendar_missing'
 WHEN prev_date<>prev_cal THEN 'not_adjacent_trading_day'
 WHEN has_event THEN 'known_corporate_action'
 WHEN candidate_return_error_pp IS NULL OR candidate_return_error_pp>0.005 THEN 'candidate_return_mismatch'
 ELSE 'internally_consistent_candidate' END decision
FROM scored
"""


def connect():
    c = duckdb.connect()
    c.execute('SET threads=2')
    c.execute("SET memory_limit='2GB'")
    return c


def prepare(c, codes):
    daily = str(SOURCE / 'tables/daily_bars/*.parquet')
    prefix = str(REPAIRS / 'prefix_v1/recovered_bar_fields.parquet')
    c.execute(f"CREATE VIEW native_daily AS SELECT {FIELDS} FROM read_parquet('{daily}') WHERE payload_encoding='msgpack'")
    c.execute(f"CREATE VIEW restored_daily AS SELECT {FIELDS} FROM read_parquet('{prefix}') WHERE source_table='daily_bars' AND eligible_overlay")
    where = ''
    if codes:
        if any(len(code) != 6 or not code.isascii() or not code.isdigit() for code in codes):
            raise ValueError('invalid code filter')
        where = ' WHERE code IN (' + ','.join("'" + code + "'" for code in codes) + ')'
    c.execute('CREATE VIEW input_daily AS SELECT * FROM native_daily' + where + ' UNION ALL SELECT * FROM restored_daily' + where)
    cal = e.pq.ParquetFile(CALENDAR).read().to_pylist()
    dates = [int(row['TradingDate']) for row in cal if row['IsTradingDay'] == 1]
    if len(dates) != len(set(dates)) or not dates:
        raise ValueError('calendar empty or duplicated')
    c.register('input_calendar', e.pa.table({'date': sorted(dates)}))
    # Even an identity-looking local action record is a reason not to auto-rebuild.
    c.execute(f"CREATE VIEW input_events AS SELECT code,date FROM read_parquet('{SOURCE}/tables/adjustment_factors/*.parquet')")


def run(output, codes):
    output = output.resolve()
    if output.exists():
        raise FileExistsError('refusing to overwrite a previous candidate run')
    inputs = sorted((SOURCE / 'tables/daily_bars').glob('*.parquet'))
    inputs += sorted((SOURCE / 'tables/adjustment_factors').glob('*.parquet'))
    inputs += [CALENDAR, REPAIRS / 'prefix_v1/recovered_bar_fields.parquet']
    hashes = {str(path): e.sha256_file(path) for path in inputs}
    c = connect()
    prepare(c, codes)
    c.execute('CREATE TEMP TABLE decisions AS ' + SQL)
    counts = c.execute('SELECT decision,count(*) FROM decisions GROUP BY decision ORDER BY decision').fetchall()
    output.mkdir(parents=True, exist_ok=False)
    name = 'preclose_candidates.parquet'
    path = output / name
    temporary = path.with_suffix('.parquet.partial')
    select = """SELECT source_db,source_file,source_sequence,logical_key,code,date,
        pre_close AS original_pre_close,prev_close AS candidate_pre_close,close,pct_chg,
        prev_logical_key,prev_source_db,prev_source_file,prev_source_sequence,prev_date,prev_cal,
        original_return_error_pp,candidate_return_error_pp,decision FROM decisions
        WHERE decision='internally_consistent_candidate' ORDER BY code,date"""
    c.execute('COPY (' + select + ') TO ? (FORMAT PARQUET,COMPRESSION ZSTD)', [str(temporary)])
    check = c.execute("""SELECT count(*),count(distinct (source_db,logical_key)),
        count_if(prev_date=prev_cal AND candidate_return_error_pp<=0.005 AND original_return_error_pp>0.2)
        FROM read_parquet(?)""", [str(temporary)]).fetchone()
    n = dict(counts).get('internally_consistent_candidate', 0)
    if check != (n, n, n):
        raise ValueError('candidate coverage/uniqueness/invariant mismatch')
    pf = e.pq.ParquetFile(temporary, page_checksum_verification=True)
    if sum(len(batch) for batch in pf.iter_batches()) != n:
        raise ValueError('candidate Parquet reopen mismatch')
    for source, before in hashes.items():
        if e.sha256_file(Path(source)) != before:
            raise ValueError('input changed: ' + source)
    temporary.rename(path)
    example = c.execute("""SELECT logical_key,pre_close,prev_close,has_event,decision
        FROM decisions WHERE code='300750' AND date=20260810""").fetchall()
    result = {'status': 'verified_isolated_preclose_candidates', 'scope_codes': codes or 'all_native_archive_codes',
              'classified_rows': sum(v for _, v in counts), 'decision_counts': dict(counts),
              'candidate_rows': n, 'source_hashes': hashes, 'script_sha256': e.sha256_file(Path(__file__)),
              'output': {'path': str(path), 'sha256': e.sha256_file(path)},
              'event_boundary_300750_20260810': example,
              'policy': 'retain original; known event, missing calendar, invalid/ambiguous predecessor rejected',
              'limit': 'internal consistency only; source price adjustment and data rights unverified; not backtest accepted'}
    e.atomic_json(output / 'validation.json', result)
    print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'}, ensure_ascii=False, indent=2), flush=True)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--codes', nargs='*')
    args = p.parse_args()
    run(args.output, args.codes)
