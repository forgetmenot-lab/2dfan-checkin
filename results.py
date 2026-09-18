"""Results shared by browser automation and notifications (no browser dependency)."""

from dataclasses import dataclass
import re


@dataclass
class CheckinResult:
    checkins_count: int = -1
    serial_checkins: int = -1
    already_done: bool = False
    points: int | None = None
    error: str | None = None
    account_name: str = ""


def parse_balance(value) -> int | None:
    """Only accept the server's user_points field, preserving a real zero balance."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    return None


def format_result(result: CheckinResult) -> str:
    if result.error:
        status = f"출석 실패: {result.error}"
    elif result.already_done:
        status = "오늘 이미 출석 완료"
    else:
        status = "출석 성공"
    days = []
    if result.checkins_count >= 0:
        days.append(f"누적 {result.checkins_count}일")
    if result.serial_checkins >= 0:
        days.append(f"연속 {result.serial_checkins}일")
    if days:
        status += " · " + " / ".join(days)
    points = f"{result.points:,}점" if result.points is not None else "조회 불가"
    return f"{status}\n보유 포인트: {points}"
