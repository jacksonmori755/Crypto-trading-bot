from enum import Enum


class RPCMessageType(Enum):
    STATUS = 'status'
    WARNING = 'warning'
    STARTUP = 'startup'

    BUY = 'buy'
    BUY_FILL = 'buy_fill'
    BUY_CANCEL = 'buy_cancel'

    SHORT = 'short'
    SHORT_FILL = 'short_fill'
    SHORT_CANCEL = 'short_cancel'

    EXIT = 'exit'
    EXIT_FILL = 'exit_fill'
    EXIT_CANCEL = 'exit_cancel'

    PROTECTION_TRIGGER = 'protection_trigger'
    PROTECTION_TRIGGER_GLOBAL = 'protection_trigger_global'

    def __repr__(self):
        return self.value

    def __str__(self):
        return self.value
