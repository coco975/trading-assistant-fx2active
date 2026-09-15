from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

FX2ACTIVE_MAGIC = 26091501
FX2ACTIVE_COMMENT = "FX2Active"


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    status: str
    message: str
    fingerprint: str
    retcode: int | None = None
    order_ticket: int | None = None
    deal_ticket: int | None = None
    volume: float | None = None
    price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionStateStore:
    """Persistent duplicate guard for broker submissions.

    A setup is recorded once MT5 accepts it, definitively rejects an OrderSend,
    or when the send result is ambiguous. This deliberately favors missing a
    retry over accidentally duplicating a broker order.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"processed": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "FX2Active execution-state file is unreadable. Order submission is blocked "
                "until the state file is inspected or repaired."
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("processed"), dict):
            raise RuntimeError(
                "FX2Active execution-state file has an invalid format. Order submission is blocked."
            )
        return payload

    def contains(self, fingerprint: str) -> bool:
        return fingerprint in self._load()["processed"]

    def record(self, fingerprint: str, result: ExecutionResult) -> None:
        payload = self._load()
        processed = payload["processed"]
        processed[fingerprint] = result.to_dict()

        if len(processed) > 500:
            for key in list(processed)[: len(processed) - 500]:
                processed.pop(key, None)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=str(self.path.parent), text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


def setup_fingerprint(symbol: str, setup: Any, execution_mode: str) -> str:
    material = "|".join(
        (
            symbol,
            str(getattr(setup, "side", "")),
            execution_mode,
            f"{float(getattr(setup, 'entry')):.10f}",
            f"{float(getattr(setup, 'stop_loss')):.10f}",
            f"{float(getattr(setup, 'take_profit')):.10f}",
            f"{float(getattr(setup, 'swing_low')):.10f}",
            f"{float(getattr(setup, 'swing_high')):.10f}",
            str(getattr(setup, "swing_low_time", "") or ""),
            str(getattr(setup, "swing_high_time", "") or ""),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _magic_matches(item: Any) -> bool:
    return int(getattr(item, "magic", 0) or 0) == FX2ACTIVE_MAGIC


def count_bot_exposure(mt5: Any, symbol: str | None = None) -> tuple[int, int]:
    """Count FX2Active-owned positions/orders, optionally restricted to one symbol.

    None from MetaTrader means the query itself failed, so fail closed instead
    of treating an API error as zero exposure.
    """

    if symbol:
        positions = mt5.positions_get(symbol=symbol)
        orders = mt5.orders_get(symbol=symbol)
    else:
        positions = mt5.positions_get()
        orders = mt5.orders_get()

    if positions is None or orders is None:
        raise RuntimeError(f"Could not read MT5 positions/orders: {mt5.last_error()}")

    position_count = sum(1 for item in positions if _magic_matches(item))
    pending_count = sum(1 for item in orders if _magic_matches(item))
    return position_count, pending_count


def _normalize_price(value: float, digits: int) -> float:
    return round(float(value), max(0, int(digits)))


def _account_is_real(mt5: Any, account: Any) -> bool | None:
    mode = getattr(account, "trade_mode", None)
    if mode is None:
        return None
    real_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 2)
    return int(mode) == int(real_mode)


def _filling_candidates(mt5: Any, info: Any, *, pending: bool) -> list[int]:
    if pending:
        return [int(getattr(mt5, "ORDER_FILLING_RETURN", 2))]

    symbol_filling = int(getattr(info, "filling_mode", 0) or 0)
    execution_mode = int(getattr(info, "trade_exemode", -1) or -1)
    candidates: list[int] = []

    symbol_ioc = int(getattr(mt5, "SYMBOL_FILLING_IOC", 2))
    symbol_fok = int(getattr(mt5, "SYMBOL_FILLING_FOK", 1))
    if symbol_filling & symbol_ioc:
        candidates.append(int(getattr(mt5, "ORDER_FILLING_IOC", 1)))
    if symbol_filling & symbol_fok:
        candidates.append(int(getattr(mt5, "ORDER_FILLING_FOK", 0)))

    market_execution = int(getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2))
    if execution_mode != market_execution:
        candidates.append(int(getattr(mt5, "ORDER_FILLING_RETURN", 2)))

    if not candidates:
        candidates.append(int(getattr(mt5, "ORDER_FILLING_IOC", 1)))

    return list(dict.fromkeys(candidates))


def _successful_send_retcodes(mt5: Any) -> set[int]:
    return {
        int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008)),
        int(getattr(mt5, "TRADE_RETCODE_DONE", 10009)),
        int(getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)),
    }


def _safe_retry_retcodes(mt5: Any) -> set[int]:
    return {
        int(getattr(mt5, "TRADE_RETCODE_REQUOTE", 10004)),
        int(getattr(mt5, "TRADE_RETCODE_PRICE_CHANGED", 10020)),
        int(getattr(mt5, "TRADE_RETCODE_PRICE_OFF", 10021)),
    }


def _result_message(result: Any) -> str:
    return str(getattr(result, "comment", "") or "MT5 rejected the trade request")


def _terminal_ready(mt5: Any) -> tuple[bool, str]:
    terminal = mt5.terminal_info()
    if terminal is None:
        return False, "MT5 terminal information is unavailable."
    if not bool(getattr(terminal, "connected", False)):
        return False, "MT5 terminal is not connected."
    if not bool(getattr(terminal, "trade_allowed", False)):
        return False, "MT5 AutoTrading is disabled."
    if bool(getattr(terminal, "tradeapi_disabled", False)):
        return False, "MT5 is blocking external Python trading access."
    return True, "MT5 terminal trading access is ready."


class WindowsTradeExecutor:
    def __init__(self, *, state_path: str | Path) -> None:
        self.state = ExecutionStateStore(state_path)

    def execute(
        self,
        *,
        mt5: Any,
        settings: Any,
        symbol: str,
        setup: Any,
        volume: float,
        pip_size: float,
        account: Any,
        symbol_info: Any,
    ) -> ExecutionResult:
        fingerprint = setup_fingerprint(symbol, setup, settings.execution_mode)

        if not settings.live_execution_enabled:
            return ExecutionResult(
                False,
                "disabled",
                "Order execution is OFF in the dashboard.",
                fingerprint,
            )
        if self.state.contains(fingerprint):
            return ExecutionResult(
                False,
                "duplicate",
                "This FX2Active setup was already submitted; duplicate order blocked.",
                fingerprint,
            )

        terminal_ok, terminal_message = _terminal_ready(mt5)
        if not terminal_ok:
            return ExecutionResult(False, "blocked", terminal_message, fingerprint)

        is_real = _account_is_real(mt5, account)
        if is_real is None and not settings.allow_live_account:
            return ExecutionResult(
                False,
                "blocked",
                "Could not verify the MT5 account type. Live-account permission is OFF.",
                fingerprint,
            )
        if is_real and not settings.allow_live_account:
            return ExecutionResult(
                False,
                "blocked",
                "This is a real/live MT5 account. Enable 'Allow real/live account' to execute.",
                fingerprint,
            )
        if not bool(getattr(account, "trade_allowed", False)):
            return ExecutionResult(False, "blocked", "MT5 account trading is not allowed.", fingerprint)
        if not bool(getattr(account, "trade_expert", True)):
            return ExecutionResult(
                False,
                "blocked",
                "MT5 account does not allow Expert Advisor/Python automated trading.",
                fingerprint,
            )

        positions, pending_orders = count_bot_exposure(mt5)
        if positions + pending_orders >= settings.max_open_positions:
            return ExecutionResult(
                False,
                "blocked",
                "FX2Active position/order limit reached.",
                fingerprint,
            )

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return ExecutionResult(False, "error", "MT5 returned no current tick.", fingerprint)

        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        if bid <= 0 or ask <= 0 or ask < bid:
            return ExecutionResult(False, "error", "MT5 returned invalid Bid/Ask prices.", fingerprint)

        spread_pips = (ask - bid) / pip_size
        if settings.max_spread_pips > 0 and spread_pips > settings.max_spread_pips:
            return ExecutionResult(
                False,
                "blocked",
                f"Spread {spread_pips:.1f} pips exceeds limit {settings.max_spread_pips:g}.",
                fingerprint,
            )

        side = str(setup.side).upper()
        if side not in {"BUY", "SELL"}:
            return ExecutionResult(False, "error", f"Unsupported side: {side}", fingerprint)

        pending = settings.execution_mode == "pending_limit"
        digits = int(getattr(symbol_info, "digits", 0) or 0)
        point = float(getattr(symbol_info, "point", 0.0) or 0.0)
        if point <= 0:
            return ExecutionResult(False, "error", "Broker returned invalid point size.", fingerprint)

        if pending:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT if side == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
            price = _normalize_price(float(setup.entry), digits)
            if side == "BUY" and price >= ask:
                return ExecutionResult(
                    False,
                    "blocked",
                    "BUY LIMIT entry is not below the current Ask price.",
                    fingerprint,
                )
            if side == "SELL" and price <= bid:
                return ExecutionResult(
                    False,
                    "blocked",
                    "SELL LIMIT entry is not above the current Bid price.",
                    fingerprint,
                )
            action = mt5.TRADE_ACTION_PENDING
        else:
            order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
            price = _normalize_price(ask if side == "BUY" else bid, digits)
            action = mt5.TRADE_ACTION_DEAL

        sl = _normalize_price(float(setup.stop_loss), digits)
        tp = _normalize_price(float(setup.take_profit), digits)
        if side == "BUY" and not (sl < price < tp):
            return ExecutionResult(False, "blocked", "BUY order has invalid SL/entry/TP order.", fingerprint)
        if side == "SELL" and not (tp < price < sl):
            return ExecutionResult(False, "blocked", "SELL order has invalid TP/entry/SL order.", fingerprint)

        stops_points = int(getattr(symbol_info, "trade_stops_level", 0) or 0)
        min_distance = max(0.0, stops_points * point)
        if min_distance > 0:
            if abs(price - sl) + 1e-12 < min_distance or abs(tp - price) + 1e-12 < min_distance:
                return ExecutionResult(
                    False,
                    "blocked",
                    f"SL/TP is inside broker minimum stop distance ({stops_points} points).",
                    fingerprint,
                )
            if pending:
                market_distance = ask - price if side == "BUY" else price - bid
                if market_distance + 1e-12 < min_distance:
                    return ExecutionResult(
                        False,
                        "blocked",
                        f"Pending entry is inside broker minimum distance ({stops_points} points).",
                        fingerprint,
                    )

        base_request = {
            "action": action,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": int(settings.max_deviation_points),
            "magic": FX2ACTIVE_MAGIC,
            "comment": FX2ACTIVE_COMMENT,
            "type_time": mt5.ORDER_TIME_GTC,
        }

        margin = mt5.order_calc_margin(order_type, symbol, float(volume), price)
        margin_free = float(getattr(account, "margin_free", 0.0) or 0.0)
        if margin is not None and float(margin) > margin_free:
            return ExecutionResult(
                False,
                "blocked",
                "Insufficient free margin for the planned FX2Active order.",
                fingerprint,
            )

        request: dict[str, Any] | None = None
        check_result: Any = None
        for filling in _filling_candidates(mt5, symbol_info, pending=pending):
            candidate = dict(base_request)
            candidate["type_filling"] = filling
            checked = mt5.order_check(candidate)
            if checked is not None and int(getattr(checked, "retcode", -1)) == 0:
                request = candidate
                check_result = checked
                break
            check_result = checked

        if request is None:
            comment = _result_message(check_result) if check_result is not None else str(mt5.last_error())
            return ExecutionResult(
                False,
                "blocked",
                f"MT5 order_check rejected the order: {comment}",
                fingerprint,
                retcode=int(getattr(check_result, "retcode", -1)) if check_result is not None else None,
            )

        attempts = 0
        while True:
            attempts += 1
            result = mt5.order_send(request)
            if result is None:
                ambiguous = ExecutionResult(
                    False,
                    "ambiguous",
                    f"MT5 order_send returned no result: {mt5.last_error()}. Duplicate retry blocked.",
                    fingerprint,
                    volume=float(volume),
                    price=float(request["price"]),
                )
                self.state.record(fingerprint, ambiguous)
                return ambiguous

            retcode = int(getattr(result, "retcode", -1))
            if retcode in _successful_send_retcodes(mt5):
                status = (
                    "placed"
                    if retcode == int(getattr(mt5, "TRADE_RETCODE_PLACED", 10008))
                    else "filled"
                )
                if retcode == int(getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)):
                    status = "partial"
                accepted = ExecutionResult(
                    True,
                    status,
                    _result_message(result) or "MT5 accepted the FX2Active order.",
                    fingerprint,
                    retcode=retcode,
                    order_ticket=int(getattr(result, "order", 0) or 0) or None,
                    deal_ticket=int(getattr(result, "deal", 0) or 0) or None,
                    volume=float(getattr(result, "volume", volume) or volume),
                    price=float(getattr(result, "price", request["price"]) or request["price"]),
                )
                self.state.record(fingerprint, accepted)
                return accepted

            if attempts <= 2 and retcode in _safe_retry_retcodes(mt5) and not pending:
                refreshed = mt5.symbol_info_tick(symbol)
                if refreshed is not None:
                    bid = float(getattr(refreshed, "bid", 0.0) or 0.0)
                    ask = float(getattr(refreshed, "ask", 0.0) or 0.0)
                    if bid <= 0 or ask <= 0 or ask < bid:
                        break
                    retry_spread = (ask - bid) / pip_size
                    if settings.max_spread_pips > 0 and retry_spread > settings.max_spread_pips:
                        return ExecutionResult(
                            False,
                            "blocked",
                            f"Spread widened to {retry_spread:.1f} pips; retry cancelled.",
                            fingerprint,
                        )
                    retry_price = _normalize_price(ask if side == "BUY" else bid, digits)
                    if side == "BUY" and not (sl < retry_price < tp):
                        break
                    if side == "SELL" and not (tp < retry_price < sl):
                        break
                    request["price"] = retry_price
                    checked = mt5.order_check(request)
                    if checked is not None and int(getattr(checked, "retcode", -1)) == 0:
                        continue

            rejected = ExecutionResult(
                False,
                "rejected",
                f"MT5 rejected the order: {_result_message(result)}",
                fingerprint,
                retcode=retcode,
                order_ticket=int(getattr(result, "order", 0) or 0) or None,
                deal_ticket=int(getattr(result, "deal", 0) or 0) or None,
                volume=float(getattr(result, "volume", 0.0) or 0.0) or None,
                price=float(getattr(result, "price", 0.0) or 0.0) or None,
            )
            self.state.record(fingerprint, rejected)
            return rejected