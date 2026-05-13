from datetime import datetime


def now() -> datetime:
    return datetime.now()


def floor_bucket(dt: datetime, seconds: int) -> datetime:
    floored_second = dt.second - (dt.second % seconds)
    return dt.replace(second=floored_second, microsecond=0)


def compute_p95(values):
    if not values:
        return None

    ordered = sorted(values)
    index = int(round(0.95 * (len(ordered) - 1)))
    return float(ordered[index])
