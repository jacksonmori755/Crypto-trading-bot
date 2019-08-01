import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from freqtrade.configuration import Arguments
from freqtrade.data import history
from freqtrade.data.btanalysis import (combine_tickers_with_mean,
                                       create_cum_profit, load_trades)
from freqtrade.exchange import Exchange
from freqtrade.resolvers import ExchangeResolver, StrategyResolver

logger = logging.getLogger(__name__)


try:
    from plotly.subplots import make_subplots
    from plotly.offline import plot
    import plotly.graph_objects as go
except ImportError:
    logger.exception("Module plotly not found \n Please install using `pip install plotly`")
    exit(1)


def init_plotscript(config):
    """
    Initialize objects needed for plotting
    :return: Dict with tickers, trades, pairs and strategy
    """
    exchange: Optional[Exchange] = None

    # Exchange is only needed when downloading data!
    if config.get("live", False) or config.get("refresh_pairs", False):
        exchange = ExchangeResolver(config.get('exchange', {}).get('name'),
                                    config).exchange

    strategy = StrategyResolver(config).strategy
    if "pairs" in config:
        pairs = config["pairs"].split(',')
    else:
        pairs = config["exchange"]["pair_whitelist"]

    # Set timerange to use
    timerange = Arguments.parse_timerange(config.get("timerange"))

    tickers = history.load_data(
        datadir=Path(str(config.get("datadir"))),
        pairs=pairs,
        ticker_interval=config['ticker_interval'],
        refresh_pairs=config.get('refresh_pairs', False),
        timerange=timerange,
        exchange=exchange,
        live=config.get("live", False),
    )

    trades = load_trades(config)
    return {"tickers": tickers,
            "trades": trades,
            "pairs": pairs,
            "strategy": strategy,
            }


def add_indicators(fig, row, indicators: List[str], data: pd.DataFrame) -> make_subplots:
    """
    Generator all the indicator selected by the user for a specific row
    :param fig: Plot figure to append to
    :param row: row number for this plot
    :param indicators: List of indicators present in the dataframe
    :param data: candlestick DataFrame
    """
    for indicator in indicators:
        if indicator in data:
            # TODO: Figure out why scattergl causes problems
            scattergl = go.Scatter(
                x=data['date'],
                y=data[indicator].values,
                mode='lines',
                name=indicator
            )
            fig.add_trace(scattergl, row, 1)
        else:
            logger.info(
                'Indicator "%s" ignored. Reason: This indicator is not found '
                'in your strategy.',
                indicator
            )

    return fig


def add_profit(fig, row, data: pd.DataFrame, column: str, name: str) -> make_subplots:
    """
    Add profit-plot
    :param fig: Plot figure to append to
    :param row: row number for this plot
    :param data: candlestick DataFrame
    :param column: Column to use for plot
    :param name: Name to use
    :return: fig with added profit plot
    """
    profit = go.Scattergl(
        x=data.index,
        y=data[column],
        name=name,
    )
    fig.add_trace(profit, row, 1)

    return fig


def plot_trades(fig, trades: pd.DataFrame) -> make_subplots:
    """
    Add trades to "fig"
    """
    # Trades can be empty
    if trades is not None and len(trades) > 0:
        trade_buys = go.Scatter(
            x=trades["open_time"],
            y=trades["open_rate"],
            mode='markers',
            name='trade_buy',
            marker=dict(
                symbol='square-open',
                size=11,
                line=dict(width=2),
                color='green'
            )
        )
        # Create description for sell summarizing the trade
        desc = trades.apply(lambda row: f"{round(row['profitperc'], 3)}%, {row['sell_reason']}, "
                                        f"{row['duration']}min",
                            axis=1)
        trade_sells = go.Scatter(
            x=trades["close_time"],
            y=trades["close_rate"],
            text=desc,
            mode='markers',
            name='trade_sell',
            marker=dict(
                symbol='square-open',
                size=11,
                line=dict(width=2),
                color='red'
            )
        )
        fig.add_trace(trade_buys, 1, 1)
        fig.add_trace(trade_sells, 1, 1)
    else:
        logger.warning("No trades found.")
    return fig


def generate_candlestick_graph(pair: str, data: pd.DataFrame, trades: pd.DataFrame = None,
                               indicators1: List[str] = [],
                               indicators2: List[str] = [],) -> go.Figure:
    """
    Generate the graph from the data generated by Backtesting or from DB
    Volume will always be ploted in row2, so Row 1 and 3 are to our disposal for custom indicators
    :param pair: Pair to Display on the graph
    :param data: OHLCV DataFrame containing indicators and buy/sell signals
    :param trades: All trades created
    :param indicators1: List containing Main plot indicators
    :param indicators2: List containing Sub plot indicators
    :return: None
    """

    # Define the graph
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        row_width=[1, 1, 4],
        vertical_spacing=0.0001,
    )
    fig['layout'].update(title=pair)
    fig['layout']['yaxis1'].update(title='Price')
    fig['layout']['yaxis2'].update(title='Volume')
    fig['layout']['yaxis3'].update(title='Other')
    fig['layout']['xaxis']['rangeslider'].update(visible=False)

    # Common information
    candles = go.Candlestick(
        x=data.date,
        open=data.open,
        high=data.high,
        low=data.low,
        close=data.close,
        name='Price'
    )
    fig.add_trace(candles, 1, 1)

    if 'buy' in data.columns:
        df_buy = data[data['buy'] == 1]
        if len(df_buy) > 0:
            buys = go.Scatter(
                x=df_buy.date,
                y=df_buy.close,
                mode='markers',
                name='buy',
                marker=dict(
                    symbol='triangle-up-dot',
                    size=9,
                    line=dict(width=1),
                    color='green',
                )
            )
            fig.add_trace(buys, 1, 1)
        else:
            logger.warning("No buy-signals found.")

    if 'sell' in data.columns:
        df_sell = data[data['sell'] == 1]
        if len(df_sell) > 0:
            sells = go.Scatter(
                x=df_sell.date,
                y=df_sell.close,
                mode='markers',
                name='sell',
                marker=dict(
                    symbol='triangle-down-dot',
                    size=9,
                    line=dict(width=1),
                    color='red',
                )
            )
            fig.add_trace(sells, 1, 1)
        else:
            logger.warning("No sell-signals found.")

    if 'bb_lowerband' in data and 'bb_upperband' in data:
        bb_lower = go.Scattergl(
            x=data.date,
            y=data.bb_lowerband,
            name='BB lower',
            line={'color': 'rgba(255,255,255,0)'},
        )
        bb_upper = go.Scattergl(
            x=data.date,
            y=data.bb_upperband,
            name='BB upper',
            fill="tonexty",
            fillcolor="rgba(0,176,246,0.2)",
            line={'color': 'rgba(255,255,255,0)'},
        )
        fig.add_trace(bb_lower, 1, 1)
        fig.add_trace(bb_upper, 1, 1)

    # Add indicators to main plot
    fig = add_indicators(fig=fig, row=1, indicators=indicators1, data=data)

    fig = plot_trades(fig, trades)

    # Volume goes to row 2
    volume = go.Bar(
        x=data['date'],
        y=data['volume'],
        name='Volume'
    )
    fig.add_trace(volume, 2, 1)

    # Add indicators to seperate row
    fig = add_indicators(fig=fig, row=3, indicators=indicators2, data=data)

    return fig


def generate_profit_graph(pairs: str, tickers: Dict[str, pd.DataFrame],
                          trades: pd.DataFrame) -> go.Figure:
    # Combine close-values for all pairs, rename columns to "pair"
    df_comb = combine_tickers_with_mean(tickers, "close")

    # Add combined cumulative profit
    df_comb = create_cum_profit(df_comb, trades, 'cum_profit')

    # Plot the pairs average close prices, and total profit growth
    avgclose = go.Scattergl(
        x=df_comb.index,
        y=df_comb['mean'],
        name='Avg close price',
    )

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_width=[1, 1, 1])
    fig['layout'].update(title="Profit plot")

    fig.add_trace(avgclose, 1, 1)
    fig = add_profit(fig, 2, df_comb, 'cum_profit', 'Profit')

    for pair in pairs:
        profit_col = f'cum_profit_{pair}'
        df_comb = create_cum_profit(df_comb, trades[trades['pair'] == pair], profit_col)

        fig = add_profit(fig, 3, df_comb, profit_col, f"Profit {pair}")

    return fig


def generate_plot_filename(pair, ticker_interval) -> str:
    """
    Generate filenames per pair/ticker_interval to be used for storing plots
    """
    pair_name = pair.replace("/", "_")
    file_name = 'freqtrade-plot-' + pair_name + '-' + ticker_interval + '.html'

    logger.info('Generate plot file for %s', pair)

    return file_name


def store_plot_file(fig, filename: str, directory: Path, auto_open: bool = False) -> None:
    """
    Generate a plot html file from pre populated fig plotly object
    :param fig: Plotly Figure to plot
    :param pair: Pair to plot (used as filename and Plot title)
    :param ticker_interval: Used as part of the filename
    :return: None
    """

    directory.mkdir(parents=True, exist_ok=True)

    plot(fig, filename=str(directory.joinpath(filename)),
         auto_open=auto_open)
