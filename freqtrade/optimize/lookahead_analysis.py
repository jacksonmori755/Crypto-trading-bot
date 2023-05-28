import copy
import logging
import pathlib
import shutil
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pandas as pd

from freqtrade.configuration import TimeRange
from freqtrade.data.history import get_timerange
from freqtrade.exchange import timeframe_to_minutes
from freqtrade.optimize.backtesting import Backtesting


logger = logging.getLogger(__name__)


class VarHolder:
    timerange: TimeRange
    data: pd.DataFrame
    indicators: pd.DataFrame
    result: pd.DataFrame
    compared: pd.DataFrame
    from_dt: datetime
    to_dt: datetime
    compared_dt: datetime
    timeframe: str


class Analysis:
    def __init__(self) -> None:
        self.total_signals = 0
        self.false_entry_signals = 0
        self.false_exit_signals = 0
        self.false_indicators: List[str] = []
        self.has_bias = False


class LookaheadAnalysis:

    def __init__(self, config: Dict[str, Any], strategy_obj: Dict):
        self.failed_bias_check = True
        self.full_varHolder = VarHolder

        self.entry_varHolders: List[VarHolder] = []
        self.exit_varHolders: List[VarHolder] = []

        # pull variables the scope of the lookahead_analysis-instance
        self.local_config = deepcopy(config)
        self.local_config['strategy'] = strategy_obj['name']
        self.current_analysis = Analysis()
        self.minimum_trade_amount = config['minimum_trade_amount']
        self.targeted_trade_amount = config['targeted_trade_amount']
        self.strategy_obj = strategy_obj

    @staticmethod
    def dt_to_timestamp(dt: datetime):
        timestamp = int(dt.replace(tzinfo=timezone.utc).timestamp())
        return timestamp

    @staticmethod
    def get_result(backtesting, processed: pd.DataFrame):
        min_date, max_date = get_timerange(processed)

        result = backtesting.backtest(
            processed=deepcopy(processed),
            start_date=min_date,
            end_date=max_date
        )
        return result

    @staticmethod
    def report_signal(result: dict, column_name: str, checked_timestamp: datetime):
        df = result['results']
        row_count = df[column_name].shape[0]

        if row_count == 0:
            return False
        else:

            df_cut = df[(df[column_name] == checked_timestamp)]
            if df_cut[column_name].shape[0] == 0:
                return False
            else:
                return True
        return False

    # analyzes two data frames with processed indicators and shows differences between them.
    def analyze_indicators(self, full_vars: VarHolder, cut_vars: VarHolder, current_pair):
        # extract dataframes
        cut_df = cut_vars.indicators[current_pair]
        full_df = full_vars.indicators[current_pair]

        # cut longer dataframe to length of the shorter
        full_df_cut = full_df[
            (full_df.date == cut_vars.compared_dt)
        ].reset_index(drop=True)
        cut_df_cut = cut_df[
            (cut_df.date == cut_vars.compared_dt)
        ].reset_index(drop=True)

        # compare dataframes
        if full_df_cut.shape[0] != 0:
            if cut_df_cut.shape[0] != 0:
                compare_df = full_df_cut.compare(cut_df_cut)

                if compare_df.shape[0] > 0:
                    for col_name, values in compare_df.items():
                        col_idx = compare_df.columns.get_loc(col_name)
                        compare_df_row = compare_df.iloc[0]
                        # compare_df now comprises tuples with [1] having either 'self' or 'other'
                        if 'other' in col_name[1]:
                            continue
                        self_value = compare_df_row[col_idx]
                        other_value = compare_df_row[col_idx + 1]

                        # output differences
                        if self_value != other_value:

                            if not self.current_analysis.false_indicators.__contains__(col_name[0]):
                                self.current_analysis.false_indicators.append(col_name[0])
                                logger.info(f"=> found look ahead bias in indicator "
                                            f"{col_name[0]}. "
                                            f"{str(self_value)} != {str(other_value)}")

    def prepare_data(self, varholder: VarHolder, pairs_to_load: List[pd.DataFrame]):

        if 'freqai' in self.local_config and 'identifier' in self.local_config['freqai']:
            # purge previous data if the freqai model is defined
            # (to be sure nothing is carried over from older backtests)
            path_to_current_identifier = (
                pathlib.Path(f"{self.local_config['user_data_dir']}"
                             "/models/"
                             f"{self.local_config['freqai']['identifier']}").resolve())
            # remove folder and its contents
            if pathlib.Path.exists(path_to_current_identifier):
                shutil.rmtree(path_to_current_identifier)

        prepare_data_config = copy.deepcopy(self.local_config)
        prepare_data_config['timerange'] = (str(self.dt_to_timestamp(varholder.from_dt)) + "-" +
                                            str(self.dt_to_timestamp(varholder.to_dt)))
        prepare_data_config['exchange']['pair_whitelist'] = pairs_to_load

        self.backtesting = Backtesting(prepare_data_config)
        self.backtesting._set_strategy(self.backtesting.strategylist[0])

        varholder.data, varholder.timerange = self.backtesting.load_bt_data()
        self.backtesting.load_bt_data_detail()
        varholder.timeframe = self.backtesting.timeframe

        varholder.indicators = self.backtesting.strategy.advise_all_indicators(varholder.data)
        varholder.result = self.get_result(self.backtesting, varholder.indicators)

    def fill_full_varholder(self):
        self.full_varHolder = VarHolder()

        # define datetime in human-readable format
        parsed_timerange = TimeRange.parse_timerange(self.local_config['timerange'])

        if parsed_timerange.startdt is None:
            self.full_varHolder.from_dt = datetime.fromtimestamp(0, tz=timezone.utc)
        else:
            self.full_varHolder.from_dt = parsed_timerange.startdt

        if parsed_timerange.stopdt is None:
            self.full_varHolder.to_dt = datetime.utcnow()
        else:
            self.full_varHolder.to_dt = parsed_timerange.stopdt

        self.prepare_data(self.full_varHolder, self.local_config['pairs'])

    def fill_entry_and_exit_varHolders(self, result_row):
        # entry_varHolder
        entry_varHolder = VarHolder()
        self.entry_varHolders.append(entry_varHolder)
        entry_varHolder.from_dt = self.full_varHolder.from_dt
        entry_varHolder.compared_dt = result_row['open_date']
        # to_dt needs +1 candle since it won't buy on the last candle
        entry_varHolder.to_dt = (
                result_row['open_date'] +
                timedelta(minutes=timeframe_to_minutes(self.full_varHolder.timeframe)))
        self.prepare_data(entry_varHolder, [result_row['pair']])

        # exit_varHolder
        exit_varHolder = VarHolder()
        self.exit_varHolders.append(exit_varHolder)
        # to_dt needs +1 candle since it will always exit/force-exit trades on the last candle
        exit_varHolder.from_dt = self.full_varHolder.from_dt
        exit_varHolder.to_dt = (
                result_row['close_date'] +
                timedelta(minutes=timeframe_to_minutes(self.full_varHolder.timeframe)))
        exit_varHolder.compared_dt = result_row['close_date']
        self.prepare_data(exit_varHolder, [result_row['pair']])

    # now we analyze a full trade of full_varholder and look for analyze its bias
    def analyze_row(self, idx, result_row):
        # if force-sold, ignore this signal since here it will unconditionally exit.
        if result_row.close_date == self.dt_to_timestamp(self.full_varHolder.to_dt):
            return

        # keep track of how many signals are processed at total
        self.current_analysis.total_signals += 1

        # fill entry_varHolder and exit_varHolder
        self.fill_entry_and_exit_varHolders(result_row)

        # register if buy signal is broken
        if not self.report_signal(
                self.entry_varHolders[idx].result,
                "open_date",
                self.entry_varHolders[idx].compared_dt):
            self.current_analysis.false_entry_signals += 1

        # register if buy or sell signal is broken
        if not self.report_signal(
                self.exit_varHolders[idx].result,
                "close_date",
                self.exit_varHolders[idx].compared_dt):
            self.current_analysis.false_exit_signals += 1

        # check if the indicators themselves contain biased data
        self.analyze_indicators(self.full_varHolder, self.entry_varHolders[idx], result_row['pair'])
        self.analyze_indicators(self.full_varHolder, self.exit_varHolders[idx], result_row['pair'])

    def start(self) -> None:

        # first make a single backtest
        self.fill_full_varholder()

        # check if requirements have been met of full_varholder
        found_signals: int = self.full_varHolder.result['results'].shape[0] + 1
        if found_signals >= self.targeted_trade_amount:
            logger.info(f"Found {found_signals} trades, "
                        f"calculating {self.targeted_trade_amount} trades.")
        elif self.targeted_trade_amount >= found_signals >= self.minimum_trade_amount:
            logger.info(f"Only found {found_signals} trades. Calculating all available trades.")
        else:
            logger.info(f"found {found_signals} trades "
                        f"which is less than minimum_trade_amount {self.minimum_trade_amount}. "
                        f"Cancelling this backtest lookahead bias test.")
            return

        # now we loop through all signals
        # starting from the same datetime to avoid miss-reports of bias
        for idx, result_row in self.full_varHolder.result['results'].iterrows():
            if self.current_analysis.total_signals == self.targeted_trade_amount:
                break
            self.analyze_row(idx, result_row)

        # check and report signals
        if self.current_analysis.total_signals < self.local_config['minimum_trade_amount']:
            logger.info(f" -> {self.local_config['strategy']} : too few trades. "
                        f"We only found {self.current_analysis.total_signals} trades. "
                        f"Hint: Extend the timerange "
                        f"to get at least {self.local_config['minimum_trade_amount']} "
                        f"or lower the value of minimum_trade_amount.")
            self.failed_bias_check = True
        elif (self.current_analysis.false_entry_signals > 0 or
              self.current_analysis.false_exit_signals > 0 or
              len(self.current_analysis.false_indicators) > 0):
            logger.info(f" => {self.local_config['strategy']} : bias detected!")
            self.current_analysis.has_bias = True
            self.failed_bias_check = False
        else:
            logger.info(self.local_config['strategy'] + ": no bias detected")
            self.failed_bias_check = False
