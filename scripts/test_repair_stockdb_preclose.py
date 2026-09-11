import unittest
import stockdb_offline_export as e
import repair_stockdb_preclose as r


def bar(date, close=10., pre_close=1., pct_chg=0., **extra):
    value = dict(source_db='data',source_file='x.ldb',source_sequence=date,
                 logical_key=f'日k:000001:{date}',code='000001',date=date,
                 open=close,high=close,low=close,close=close,pre_close=pre_close,pct_chg=pct_chg)
    value.update(extra)
    return value


class Rules(unittest.TestCase):
    def classify(self, rows, dates=(20260105,20260106), events=()):
        c=r.connect()
        c.register('input_daily',e.pa.Table.from_pylist(rows))
        c.register('input_calendar',e.pa.table({'date':list(dates)}))
        c.register('input_events',e.pa.table({'code':e.pa.array(['000001']*len(events),type=e.pa.string()),
                                             'date':e.pa.array(list(events),type=e.pa.int64())}))
        return c.execute('SELECT date,decision FROM ('+r.SQL+') ORDER BY date').fetchall()

    def test_ordinary_day(self):
        self.assertEqual(self.classify([bar(20260105),bar(20260106)])[-1][1],'internally_consistent_candidate')

    def test_calendar_first_day_fails_closed(self):
        self.assertEqual(self.classify([bar(20260104),bar(20260105)])[-1][1],'calendar_or_previous_calendar_missing')

    def test_empty_current_ohlc_fails_closed(self):
        self.assertEqual(self.classify([bar(20260105),bar(20260106,open=None)])[-1][1],'invalid_current_ohlc')

    def test_invalid_previous_fails_closed(self):
        self.assertEqual(self.classify([bar(20260105,high=1.),bar(20260106)])[-1][1],'invalid_previous_ohlc')

    def test_duplicate_previous_fails_closed(self):
        self.assertEqual(self.classify([bar(20260105),bar(20260105,source_db='data1'),bar(20260106)])[-1][1],'ambiguous_previous_record')

    def test_event_rejects_even_duplicated_event_rows(self):
        result=self.classify([bar(20260105),bar(20260106)],events=(20260106,20260106))
        self.assertEqual(len(result),2)
        self.assertEqual(result[-1][1],'known_corporate_action')

    def test_original_consistent_and_rounding_left_unchanged(self):
        self.assertEqual(self.classify([bar(20260105),bar(20260106,pre_close=10.)])[-1][1],'original_within_existing_qc_tolerance')

    def test_return_mismatch_and_missing_day(self):
        self.assertEqual(self.classify([bar(20260105),bar(20260106,pct_chg=10.)])[-1][1],'candidate_return_mismatch')
        self.assertEqual(self.classify([bar(20260101),bar(20260106)])[-1][1],'not_adjacent_trading_day')


if __name__=='__main__':
    unittest.main()
