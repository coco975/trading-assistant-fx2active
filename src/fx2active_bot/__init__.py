from . import mac_bridge as _mac_bridge
from .bridge_version import BRIDGE_SOURCE_VERSION
from .config import StrategyConfig
from .fibonacci import BearishFibLevels, BullishFibLevels, bearish_fib_levels, bullish_fib_levels
from .models import Candle
from .strategy import DualFibStrategy, LongFibStrategy, ShortFibStrategy, TradeSetup

# mac_bridge predates the centralized release constant. Keep its public constant
# synchronized for callers that still import it from that module.
_mac_bridge.BRIDGE_SOURCE_VERSION = BRIDGE_SOURCE_VERSION

__all__ = [
    "BRIDGE_SOURCE_VERSION",
    "BearishFibLevels",
    "BullishFibLevels",
    "Candle",
    "DualFibStrategy",
    "LongFibStrategy",
    "ShortFibStrategy",
    "StrategyConfig",
    "TradeSetup",
    "bearish_fib_levels",
    "bullish_fib_levels",
]
