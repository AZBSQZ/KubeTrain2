from datetime import datetime


def format_datetime(dt):
    if dt is None:
        return None
    return dt.isoformat() + 'Z'
