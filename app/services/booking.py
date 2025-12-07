from typing import List, Dict, Optional

def compute_availability(
    time_min_iso: str,
    time_max_iso: str,
    slot_minutes: int,
    capacity_per_slot: int,
    events: List[Dict],
    timezone: Optional[str] = None,
    available_windows: Optional[List[Dict]] = None,
    extra_occupied: Optional[Dict[str, int]] = None,
    min_notice_minutes: Optional[int] = None,
    max_future_days: Optional[int] = None,
) -> List[Dict]:
    import datetime
    tmn = datetime.datetime.fromisoformat(time_min_iso.replace("Z", "+00:00"))
    tmx = datetime.datetime.fromisoformat(time_max_iso.replace("Z", "+00:00"))
    if tmn.tzinfo is None:
        tmn = tmn.replace(tzinfo=datetime.timezone.utc)
    if tmx.tzinfo is None:
        tmx = tmx.replace(tzinfo=datetime.timezone.utc)
    occupied = dict(extra_occupied or {})
    for ev in events:
        try:
            si = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
            if si:
                occupied.setdefault(si, 0)
                occupied[si] = int(occupied.get(si, 0)) + 1
        except Exception:
            pass

    def in_business_hours(dt: datetime.datetime) -> bool:
        if not available_windows:
            return True
        try:
            # Convert to target timezone if provided
            if timezone:
                try:
                    import zoneinfo
                    tz = zoneinfo.ZoneInfo(timezone)
                    local = dt.astimezone(tz)
                except Exception:
                    local = dt
            else:
                local = dt
            day = ["mon","tue","wed","thu","fri","sat","sun"][local.weekday()]
            hh = local.hour; mm = local.minute
            minutes = hh*60 + mm
            for w in available_windows:
                try:
                    d = (w.get("day") or "").strip().lower()[:3]
                    if d != day:
                        continue
                    sh, sm = [int(x) for x in (w.get("start") or "00:00").split(":", 1)]
                    eh, em = [int(x) for x in (w.get("end") or "23:59").split(":", 1)]
                    if (eh*60+em) <= (sh*60+sm):
                        continue
                    if minutes >= (sh*60+sm) and minutes < (eh*60+em):
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return True

    now = datetime.datetime.now(datetime.timezone.utc)
    if min_notice_minutes and isinstance(min_notice_minutes, int):
        now = now + datetime.timedelta(minutes=min_notice_minutes)
    max_future_limit = None
    if max_future_days and isinstance(max_future_days, int):
        max_future_limit = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=max_future_days)

    avail = []
    cur_t = tmn
    while cur_t < tmx:
        end_t = cur_t + datetime.timedelta(minutes=int(slot_minutes or 30))
        if end_t.tzinfo is None:
            end_t = end_t.replace(tzinfo=datetime.timezone.utc)
        key = cur_t.isoformat()
        key2 = key.replace("+00:00", "")
        occ = int(occupied.get(key, occupied.get(key2, 0)))
        if occ < int(capacity_per_slot or 1):
            if in_business_hours(cur_t):
                if (cur_t >= now) and (max_future_limit is None or cur_t <= max_future_limit):
                    avail.append({"start": cur_t.isoformat(), "end": end_t.isoformat()})
        cur_t = end_t
    return avail
