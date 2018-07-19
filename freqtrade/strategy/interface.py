"""
IStrategy interface
This module defines the interface to apply for strategies
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Dict, List, Tuple

import arrow
from pandas import DataFrame

from freqtrade import constants
from freqtrade.exchange.exchange_helpers import parse_ticker_dataframe
from freqtrade.exchange import Exchange
from freqtrade.persistence import Trade

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """
    Enum to distinguish between buy and sell signals
    """
    BUY = "buy"
    SELL = "sell"


class IStrategy(ABC):
    """
    Interface for freqtrade strategies
    Defines the mandatory structure must follow any custom strategies

    Attributes you can use:
        minimal_roi -> Dict: Minimal ROI designed for the strategy
        stoploss -> float: optimal stoploss designed for the strategy
        ticker_interval -> str: value of the ticker interval to use for the strategy
    """

    minimal_roi: Dict
    stoploss: float
    ticker_interval: str

    def __init__(self, config: dict) -> None:
        self.config = config

    @abstractmethod
    def populate_indicators(self, dataframe: DataFrame) -> DataFrame:
        """
        Populate indicators that will be used in the Buy and Sell strategy
        :param dataframe: Raw data from the exchange and parsed by parse_ticker_dataframe()
        :return: a Dataframe with all mandatory indicators for the strategies
        """

    @abstractmethod
    def populate_buy_trend(self, dataframe: DataFrame) -> DataFrame:
        """
        Based on TA indicators, populates the buy signal for the given dataframe
        :param dataframe: DataFrame
        :return: DataFrame with buy column
        """

    @abstractmethod
    def populate_sell_trend(self, dataframe: DataFrame) -> DataFrame:
        """
        Based on TA indicators, populates the sell signal for the given dataframe
        :param dataframe: DataFrame
        :return: DataFrame with sell column
        """

    def analyze_ticker(self, ticker_history: List[Dict]) -> DataFrame:
        """
        Parses the given ticker history and returns a populated DataFrame
        add several TA indicators and buy signal to it
        :return DataFrame with ticker data and indicator data
        """
        dataframe = parse_ticker_dataframe(ticker_history)
        dataframe = self.populate_indicators(dataframe)
        dataframe = self.populate_buy_trend(dataframe)
        dataframe = self.populate_sell_trend(dataframe)
        return dataframe

    def get_signal(self, exchange: Exchange, pair: str, interval: str) -> Tuple[bool, bool]:
        """
        Calculates current signal based several technical analysis indicators
        :param pair: pair in format ANT/BTC
        :param interval: Interval to use (in min)
        :return: (Buy, Sell) A bool-tuple indicating buy/sell signal
        """
        ticker_hist = exchange.get_ticker_history(pair, interval)
        if not ticker_hist:
            logger.warning('Empty ticker history for pair %s', pair)
            return False, False

        try:
            dataframe = self.analyze_ticker(ticker_hist)
        except ValueError as error:
            logger.warning(
                'Unable to analyze ticker for pair %s: %s',
                pair,
                str(error)
            )
            return False, False
        except Exception as error:
            logger.exception(
                'Unexpected error when analyzing ticker for pair %s: %s',
                pair,
                str(error)
            )
            return False, False

        if dataframe.empty:
            logger.warning('Empty dataframe for pair %s', pair)
            return False, False

        latest = dataframe.iloc[-1]

        # Check if dataframe is out of date
        signal_date = arrow.get(latest['date'])
        interval_minutes = constants.TICKER_INTERVAL_MINUTES[interval]
        if signal_date < (arrow.utcnow().shift(minutes=-(interval_minutes * 2 + 5))):
            logger.warning(
                'Outdated history for pair %s. Last tick is %s minutes old',
                pair,
                (arrow.utcnow() - signal_date).seconds // 60
            )
            return False, False

        (buy, sell) = latest[SignalType.BUY.value] == 1, latest[SignalType.SELL.value] == 1
        logger.debug(
            'trigger: %s (pair=%s) buy=%s sell=%s',
            latest['date'],
            pair,
            str(buy),
            str(sell)
        )
        return buy, sell

    def should_sell(self, trade: Trade, rate: float, date: datetime, buy: bool, sell: bool) -> bool:
        """
        This function evaluate if on the condition required to trigger a sell has been reached
        if the threshold is reached and updates the trade record.
        :return: True if trade should be sold, False otherwise
        """
        current_profit = trade.calc_profit_percent(rate)
        if self.stop_loss_reached(current_rate=rate, trade=trade, current_time=date,
                                  current_profit=current_profit):
            return True

        experimental = self.config.get('experimental', {})

        if buy and experimental.get('ignore_roi_if_buy_signal', False):
            logger.debug('Buy signal still active - not selling.')
            return False

        # Check if minimal roi has been reached and no longer in buy conditions (avoiding a fee)
        if self.min_roi_reached(trade=trade, current_profit=current_profit, current_time=date):
            logger.debug('Required profit reached. Selling..')
            return True

        if experimental.get('sell_profit_only', False):
            logger.debug('Checking if trade is profitable..')
            if trade.calc_profit(rate=rate) <= 0:
                return False
        if sell and not buy and experimental.get('use_sell_signal', False):
            logger.debug('Sell signal received. Selling..')
            return True

        return False

    def stop_loss_reached(self, current_rate: float, trade: Trade, current_time: datetime,
                          current_profit: float) -> bool:
        """
        Based on current profit of the trade and configured (trailing) stoploss,
        decides to sell or not
        :param current_profit: current profit in percent
        """

        trailing_stop = self.config.get('trailing_stop', False)

        trade.adjust_stop_loss(trade.open_rate, self.stoploss, initial=True)

        # evaluate if the stoploss was hit
        if self.stoploss is not None and trade.stop_loss >= current_rate:

            if trailing_stop:
                logger.debug(
                    f"HIT STOP: current price at {current_rate:.6f}, "
                    f"stop loss is {trade.stop_loss:.6f}, "
                    f"initial stop loss was at {trade.initial_stop_loss:.6f}, "
                    f"trade opened at {trade.open_rate:.6f}")
                logger.debug(f"trailing stop saved {trade.stop_loss - trade.initial_stop_loss:.6f}")

            logger.debug('Stop loss hit.')
            return True

        # update the stop loss afterwards, after all by definition it's supposed to be hanging
        if trailing_stop:

            # check if we have a special stop loss for positive condition
            # and if profit is positive
            stop_loss_value = self.stoploss
            sl_offset = self.config.get('trailing_stop_positive_offset', 0.0)

            if 'trailing_stop_positive' in self.config and current_profit > sl_offset:

                # Ignore mypy error check in configuration that this is a float
                stop_loss_value = self.config.get('trailing_stop_positive')  # type: ignore
                logger.debug(f"using positive stop loss mode: {stop_loss_value} "
                             f"with offset {sl_offset:.4g} "
                             f"since we have profit {current_profit:.4f}%")

            trade.adjust_stop_loss(current_rate, stop_loss_value)

        return False

    def min_roi_reached(self, trade: Trade, current_profit: float, current_time: datetime) -> bool:
        """
        Based an earlier trade and current price and ROI configuration, decides whether bot should
        sell
        :return True if bot should sell at current rate
        """

        # Check if time matches and current rate is above threshold
        time_diff = (current_time.timestamp() - trade.open_date.timestamp()) / 60
        for duration, threshold in self.minimal_roi.items():
            if time_diff <= duration:
                return False
            if current_profit > threshold:
                return True

        return False

    def tickerdata_to_dataframe(self, tickerdata: Dict[str, List]) -> Dict[str, DataFrame]:
        """
        Creates a dataframe and populates indicators for given ticker data
        """
        return {pair: self.populate_indicators(parse_ticker_dataframe(pair_data))
                for pair, pair_data in tickerdata.items()}
