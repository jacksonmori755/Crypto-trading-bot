import logging
from pathlib import Path
from typing import Dict

from pandas import DataFrame

from freqtrade.constants import LAST_BT_RESULT_FN
from freqtrade.misc import file_dump_joblib, file_dump_json
from freqtrade.optimize.backtest_caching import get_backtest_metadata_filename


logger = logging.getLogger(__name__)


def store_backtest_stats(
        recordfilename: Path, stats: Dict[str, DataFrame], dtappendix: str) -> None:
    """
    Stores backtest results
    :param recordfilename: Path object, which can either be a filename or a directory.
        Filenames will be appended with a timestamp right before the suffix
        while for directories, <directory>/backtest-result-<datetime>.json will be used as filename
    :param stats: Dataframe containing the backtesting statistics
    :param dtappendix: Datetime to use for the filename
    """
    if recordfilename.is_dir():
        filename = (recordfilename / f'backtest-result-{dtappendix}.json')
    else:
        filename = Path.joinpath(
            recordfilename.parent, f'{recordfilename.stem}-{dtappendix}'
        ).with_suffix(recordfilename.suffix)

    # Store metadata separately.
    file_dump_json(get_backtest_metadata_filename(filename), stats['metadata'])
    del stats['metadata']

    file_dump_json(filename, stats)

    latest_filename = Path.joinpath(filename.parent, LAST_BT_RESULT_FN)
    file_dump_json(latest_filename, {'latest_backtest': str(filename.name)})


def _store_backtest_analysis_data(
        recordfilename: Path, data: Dict[str, Dict],
        dtappendix: str, name: str) -> Path:
    """
    Stores backtest trade candles for analysis
    :param recordfilename: Path object, which can either be a filename or a directory.
        Filenames will be appended with a timestamp right before the suffix
        while for directories, <directory>/backtest-result-<datetime>_<name>.pkl will be used
        as filename
    :param candles: Dict containing the backtesting data for analysis
    :param dtappendix: Datetime to use for the filename
    :param name: Name to use for the file, e.g. signals, rejected
    """
    if recordfilename.is_dir():
        filename = (recordfilename / f'backtest-result-{dtappendix}_{name}.pkl')
    else:
        filename = Path.joinpath(
            recordfilename.parent, f'{recordfilename.stem}-{dtappendix}_{name}.pkl'
        )

    file_dump_joblib(filename, data)

    return filename


def store_backtest_analysis_results(
        recordfilename: Path, candles: Dict[str, Dict], trades: Dict[str, Dict],
        dtappendix: str) -> None:
    _store_backtest_analysis_data(recordfilename, candles, dtappendix, "signals")
    _store_backtest_analysis_data(recordfilename, trades, dtappendix, "rejected")
