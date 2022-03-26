# Strategy Migration between V2 and V3

We have put a great effort into keeping compatibility with existing strategies, so if you just want to continue using freqtrade in spot markets, there should be no changes necessary for now.

To support new markets and trade-types (namely short trades / trades with leverage), some things had to change in the interface.
If you intend on using markets other than spot markets, please migrate your strategy to the new format.

## Quick summary / migration checklist

* Strategy methods:
  * `populate_buy_trend()` -> `populate_entry_trend()`
  * `populate_sell_trend()` -> `populate_exit_trend()`
  * `custom_sell()` -> `custom_exit()`
  * `check_buy_timeout()` -> `check_entry_timeout()`
  * `check_sell_timeout()` -> `check_exit_timeout()`
* Dataframe columns:
  * `buy` -> `enter_long`
  * `sell` -> `exit_long`
  * `buy_tag` -> `enter_tag` (used for both long and short trades)
  * New column `enter_short` and corresponding new column `exit_short`
* trade-object now has the following new properties: `is_short`, `enter_side`, `exit_side` and `trade_direction`.
* New `side` argument to callbacks without trade object
  * `custom_stake_amount`
  * `confirm_trade_entry`
* Changed argument name in `confirm_trade_exit`
* Renamed `trade.nr_of_successful_buys` to `trade.nr_of_successful_entries` (mostly relevant for `adjust_trade_position()`).
* Introduced new [`leverage` callback](strategy-callbacks.md#leverage-callback).
* Informative pairs can now pass a 3rd element in the Tuple, defining the candle type.
* `@informative` decorator now takes an optional `candle_type` argument.
* helper methods `stoploss_from_open` and `stoploss_from_absolute` now take `is_short` as additional argument.
* `INTERFACE_VERSION` should be set to 3.
* Strategy/Configuration settings.
  * `order_time_in_force` buy -> entry, sell -> exit.
  * `order_types` buy -> entry, sell -> exit.
  * `unfilledtimeout` buy -> entry, sell -> exit.

## Extensive explanation

### `populate_buy_trend`

In `populate_buy_trend()` - you will want to change the columns you assign from `'buy`' to `'enter_long`, as well as the method name from `populate_buy_trend` to `populate_entry_trend`.

```python hl_lines="1 9"
def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe.loc[
        (
            (qtpylib.crossed_above(dataframe['rsi'], 30)) &  # Signal: RSI crosses above 30
            (dataframe['tema'] <= dataframe['bb_middleband']) &  # Guard
            (dataframe['tema'] > dataframe['tema'].shift(1)) &  # Guard
            (dataframe['volume'] > 0)  # Make sure Volume is not 0
        ),
        ['buy', 'buy_tag']] = (1, 'rsi_cross')

    return dataframe
```

After:

```python hl_lines="1 9"
def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe.loc[
        (
            (qtpylib.crossed_above(dataframe['rsi'], 30)) &  # Signal: RSI crosses above 30
            (dataframe['tema'] <= dataframe['bb_middleband']) &  # Guard
            (dataframe['tema'] > dataframe['tema'].shift(1)) &  # Guard
            (dataframe['volume'] > 0)  # Make sure Volume is not 0
        ),
        ['enter_long', 'enter_tag']] = (1, 'rsi_cross')

    return dataframe
```

Please refer to the [Strategy documentation](strategy-customization.md#entry-signal-rules) on how to enter and exit short trades.

### `populate_sell_trend`

Similar to `populate_buy_trend`, `populate_sell_trend()` will be renamed to `populate_exit_trend()`.
We'll also change the column from `"sell"` to `"exit_long"`.

``` python hl_lines="1 9"
def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe.loc[
        (
            (qtpylib.crossed_above(dataframe['rsi'], 70)) &  # Signal: RSI crosses above 70
            (dataframe['tema'] > dataframe['bb_middleband']) &  # Guard
            (dataframe['tema'] < dataframe['tema'].shift(1)) &  # Guard
            (dataframe['volume'] > 0)  # Make sure Volume is not 0
        ),
        ['sell', 'exit_tag']] = (1, 'some_exit_tag')
    return dataframe
```

After

``` python hl_lines="1 9"
def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe.loc[
        (
            (qtpylib.crossed_above(dataframe['rsi'], 70)) &  # Signal: RSI crosses above 70
            (dataframe['tema'] > dataframe['bb_middleband']) &  # Guard
            (dataframe['tema'] < dataframe['tema'].shift(1)) &  # Guard
            (dataframe['volume'] > 0)  # Make sure Volume is not 0
        ),
        ['exit_long', 'exit_tag']] = (1, 'some_exit_tag')
    return dataframe
```

Please refer to the [Strategy documentation](strategy-customization.md#exit-signal-rules) on how to enter and exit short trades.

### `custom_sell`

``` python hl_lines="2"
class AwesomeStrategy(IStrategy):
    def custom_sell(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        # ...
```

``` python hl_lines="2"
class AwesomeStrategy(IStrategy):
    def custom_exit(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        # ...
```

### `custom_entry_timeout`

`check_buy_timeout()` has been renamed to `check_entry_timeout()`, and `check_sell_timeout()` has been renamed to `check_exit_timeout()`.

``` python hl_lines="2 6"
class AwesomeStrategy(IStrategy):
    def check_buy_timeout(self, pair: str, trade: 'Trade', order: dict, 
                            current_time: datetime, **kwargs) -> bool:
        return False

    def check_sell_timeout(self, pair: str, trade: 'Trade', order: dict, 
                            current_time: datetime, **kwargs) -> bool:
        return False 
```

``` python hl_lines="2 6"
class AwesomeStrategy(IStrategy):
    def check_entry_timeout(self, pair: str, trade: 'Trade', order: dict, 
                            current_time: datetime, **kwargs) -> bool:
        return False

    def check_exit_timeout(self, pair: str, trade: 'Trade', order: dict, 
                            current_time: datetime, **kwargs) -> bool:
        return False 
```

### Custom-stake-amount

New string argument `side` - which can be either `"long"` or `"short"`.

``` python hl_lines="4"
class AwesomeStrategy(IStrategy):
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float, max_stake: float,
                            entry_tag: Optional[str], **kwargs) -> float:
        # ... 
        return proposed_stake
```

``` python hl_lines="4"
class AwesomeStrategy(IStrategy):
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float, max_stake: float,
                            entry_tag: Optional[str], side: str, **kwargs) -> float:
        # ... 
        return proposed_stake
```

### `confirm_trade_entry`

New string argument `side` - which can be either `"long"` or `"short"`.

``` python hl_lines="4"
class AwesomeStrategy(IStrategy):
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                            **kwargs) -> bool:
      return True
```

After: 

``` python hl_lines="4"
class AwesomeStrategy(IStrategy):
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                            side: str, **kwargs) -> bool:
      return True
```

### `confirm_trade_exit`

Changed argument `sell_reason` to `exit_reason`.
For compatibility, `sell_reason` will still be provided for a limited time.

``` python hl_lines="3"
class AwesomeStrategy(IStrategy):
    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                           rate: float, time_in_force: str, sell_reason: str,
                           current_time: datetime, **kwargs) -> bool:
    return True
```

After:

``` python hl_lines="3"
class AwesomeStrategy(IStrategy):
    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:
    return True
```

### Adjust trade position changes

While adjust-trade-position itself did not change, you should no longer use `trade.nr_of_successful_buys` - and instead use `trade.nr_of_successful_entries`, which will also include short entries.

### Helper methods

Added argument "is_short" to `stoploss_from_open` and `stoploss_from_absolute`.
This should be given the value of `trade.is_short`.

``` python hl_lines="5 7"
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        # once the profit has risen above 10%, keep the stoploss at 7% above the open price
        if current_profit > 0.10:
            return stoploss_from_open(0.07, current_profit)

        return stoploss_from_absolute(current_rate - (candle['atr'] * 2), current_rate)

        return 1

```

``` python hl_lines="5 7"
    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        # once the profit has risen above 10%, keep the stoploss at 7% above the open price
        if current_profit > 0.10:
            return stoploss_from_open(0.07, current_profit, is_short=trade.is_short)

        return stoploss_from_absolute(current_rate - (candle['atr'] * 2), current_rate, is_short=trade.is_short)


```

### Strategy/Configuration settings

#### `order_time_in_force`

`order_time_in_force` attributes changed from `"buy"` to `"entry"` and `"sell"` to `"exit"`.

``` python
    order_time_in_force: Dict = {
        "buy": "gtc",
        "sell": "gtc",
    }
```

``` python hl_lines="2 3"
    order_time_in_force: Dict = {
        "entry": "gtc",
        "exit": "gtc",
    }
```

#### `order_types`

`order_types` have changed all wordings from `buy` to `entry` - and `sell` to `exit`.

``` python hl_lines="2-6"
    order_types = {
        "buy": "limit",
        "sell": "limit",
        "emergencysell": "market",
        "forcesell": "market",
        "forcebuy": "market",
        "stoploss": "market",
        "stoploss_on_exchange": false,
        "stoploss_on_exchange_interval": 60
    }
```

``` python hl_lines="2-6"
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "emergencyexit": "market",
        "forceexit": "market",
        "forceentry": "market",
        "stoploss": "market",
        "stoploss_on_exchange": false,
        "stoploss_on_exchange_interval": 60
    }
```

#### `unfilledtimeout`

`unfilledtimeout` have changed all wordings from `buy` to `entry` - and `sell` to `exit`.

``` python hl_lines="2-3"
unfilledtimeout = {
        "buy": 10,
        "sell": 10,
        "exit_timeout_count": 0,
        "unit": "minutes"
    }
```

``` python hl_lines="2-3"
unfilledtimeout = {
        "entry": 10,
        "exit": 10,
        "exit_timeout_count": 0,
        "unit": "minutes"
    }
```
