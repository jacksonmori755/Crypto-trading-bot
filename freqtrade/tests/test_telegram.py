import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from jsonschema import validate
from telegram import Bot, Update, Message, Chat

from freqtrade import exchange
from freqtrade.main import init, create_trade
from freqtrade.misc import update_state, State, get_state, CONF_SCHEMA
from freqtrade.persistence import Trade
from freqtrade.rpc.telegram import _status, _profit, _forcesell, _performance, _start, _stop


class MagicBot(MagicMock, Bot):
    pass


class TestTelegram(unittest.TestCase):

    conf = {
        "max_open_trades": 3,
        "stake_currency": "BTC",
        "stake_amount": 0.05,
        "dry_run": True,
        "minimal_roi": {
            "2880": 0.005,
            "720": 0.01,
            "0": 0.02
        },
        "bid_strategy": {
            "ask_last_balance": 0.0
        },
        "bittrex": {
            "enabled": True,
            "key": "key",
            "secret": "secret",
            "pair_whitelist": [
                "BTC_ETH"
            ]
        },
        "telegram": {
            "enabled": True,
            "token": "token",
            "chat_id": "0"
        },
        "initial_state": "running"
    }

    def test_1_status_handle(self):
        with patch.dict('freqtrade.main._CONF', self.conf):
            with patch('freqtrade.main.get_buy_signal', side_effect=lambda _: True):
                msg_mock = MagicMock()
                with patch.multiple('freqtrade.main.telegram', _CONF=self.conf, init=MagicMock(), send_msg=msg_mock):
                    with patch.multiple('freqtrade.main.exchange',
                                        get_ticker=MagicMock(return_value={
                                            'bid': 0.07256061,
                                            'ask': 0.072661,
                                            'last': 0.07256061
                                        }),
                                        buy=MagicMock(return_value='mocked_order_id')):
                        init(self.conf, 'sqlite://')

                        # Create some test data
                        trade = create_trade(15.0, exchange.Exchange.BITTREX)
                        assert trade
                        Trade.session.add(trade)
                        Trade.session.flush()

                        _status(bot=MagicBot(), update=self.update)
                        assert msg_mock.call_count == 2
                        assert '[BTC_ETH]' in msg_mock.call_args_list[-1][0][0]

    def test_2_profit_handle(self):
        with patch.dict('freqtrade.main._CONF', self.conf):
            with patch('freqtrade.main.get_buy_signal', side_effect=lambda _: True):
                msg_mock = MagicMock()
                with patch.multiple('freqtrade.main.telegram', _CONF=self.conf, init=MagicMock(), send_msg=msg_mock):
                    with patch.multiple('freqtrade.main.exchange',
                                        get_ticker=MagicMock(return_value={
                                            'bid': 0.07256061,
                                            'ask': 0.072661,
                                            'last': 0.07256061
                                        }),
                                        buy=MagicMock(return_value='mocked_order_id')):
                        init(self.conf, 'sqlite://')

                        # Create some test data
                        trade = create_trade(15.0, exchange.Exchange.BITTREX)
                        assert trade
                        trade.close_rate = 0.07256061
                        trade.close_profit = 100.00
                        trade.close_date = datetime.utcnow()
                        trade.open_order_id = None
                        trade.is_open = False
                        Trade.session.add(trade)
                        Trade.session.flush()

                        _profit(bot=MagicBot(), update=self.update)
                        assert msg_mock.call_count == 2
                        assert '(100.00%)' in msg_mock.call_args_list[-1][0][0]

    def test_3_forcesell_handle(self):
        with patch.dict('freqtrade.main._CONF', self.conf):
            with patch('freqtrade.main.get_buy_signal', side_effect=lambda _: True):
                msg_mock = MagicMock()
                with patch.multiple('freqtrade.main.telegram', _CONF=self.conf, init=MagicMock(), send_msg=msg_mock):
                    with patch.multiple('freqtrade.main.exchange',
                                        get_ticker=MagicMock(return_value={
                                            'bid': 0.07256061,
                                            'ask': 0.072661,
                                            'last': 0.07256061
                                        }),
                                        buy=MagicMock(return_value='mocked_order_id')):
                        init(self.conf, 'sqlite://')

                        # Create some test data
                        trade = create_trade(15.0, exchange.Exchange.BITTREX)
                        assert trade
                        Trade.session.add(trade)
                        Trade.session.flush()

                        self.update.message.text = '/forcesell 1'
                        _forcesell(bot=MagicBot(), update=self.update)

                        assert msg_mock.call_count == 2
                        assert 'Selling [BTC/ETH]' in msg_mock.call_args_list[-1][0][0]
                        assert '0.072561' in msg_mock.call_args_list[-1][0][0]

    def test_4_performance_handle(self):
        with patch.dict('freqtrade.main._CONF', self.conf):
            with patch('freqtrade.main.get_buy_signal', side_effect=lambda _: True):
                msg_mock = MagicMock()
                with patch.multiple('freqtrade.main.telegram', _CONF=self.conf, init=MagicMock(), send_msg=msg_mock):
                    with patch.multiple('freqtrade.main.exchange',
                                        get_ticker=MagicMock(return_value={
                                            'bid': 0.07256061,
                                            'ask': 0.072661,
                                            'last': 0.07256061
                                        }),
                                        buy=MagicMock(return_value='mocked_order_id')):
                        init(self.conf, 'sqlite://')

                        # Create some test data
                        trade = create_trade(15.0, exchange.Exchange.BITTREX)
                        assert trade
                        trade.close_rate = 0.07256061
                        trade.close_profit = 100.00
                        trade.close_date = datetime.utcnow()
                        trade.open_order_id = None
                        trade.is_open = False
                        Trade.session.add(trade)
                        Trade.session.flush()

                        _performance(bot=MagicBot(), update=self.update)
                        assert msg_mock.call_count == 2
                        assert 'Performance' in msg_mock.call_args_list[-1][0][0]
                        assert 'BTC_ETH	100.00%' in msg_mock.call_args_list[-1][0][0]

    def test_5_start_handle(self):
        with patch.dict('freqtrade.main._CONF', self.conf):
            msg_mock = MagicMock()
            with patch.multiple('freqtrade.main.telegram', _CONF=self.conf, init=MagicMock(), send_msg=msg_mock):
                init(self.conf, 'sqlite://')

                update_state(State.STOPPED)
                assert get_state() == State.STOPPED
                _start(bot=MagicBot(), update=self.update)
                assert get_state() == State.RUNNING
                assert msg_mock.call_count == 0

    def test_6_stop_handle(self):
        with patch.dict('freqtrade.main._CONF', self.conf):
            msg_mock = MagicMock()
            with patch.multiple('freqtrade.main.telegram', _CONF=self.conf, init=MagicMock(), send_msg=msg_mock):
                init(self.conf, 'sqlite://')

                update_state(State.RUNNING)
                assert get_state() == State.RUNNING
                _stop(bot=MagicBot(), update=self.update)
                assert get_state() == State.STOPPED
                assert msg_mock.call_count == 1
                assert 'Stopping trader' in msg_mock.call_args_list[0][0][0]

    def setUp(self):
        self.update = Update(0)
        self.update.message = Message(0, 0, datetime.utcnow(), Chat(0, 0))

    @classmethod
    def setUpClass(cls):
        validate(cls.conf, CONF_SCHEMA)


if __name__ == '__main__':
    unittest.main()
