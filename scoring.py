

def format_points(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return str(int(number))
    return f"{number:g}"


def displayed_total(raw_total):
    try:
        return max(0.0, float(raw_total or 0))
    except (TypeError, ValueError):
        return 0.0


def applied_points(order_kind, configured_points, current_total=0):
    del current_total
    points = abs(float(configured_points))
    if order_kind == "reprimand":
        return -points
    return points


def format_achievement_line(item):
    number = item.get("order_number") or "Б/Н"
    date = item.get("order_date") or ""
    date_part = f" від {date}" if date and date != "Не вказана" else ""

    points_list = item.get("commendation_points") or []
    if len(points_list) > 1:
        pts_text = "+".join(format_points(p) for p in points_list)
        return f"№{number}{date_part} ({pts_text})"

    pts = float(item.get("points") or 0)
    pts_text = format_points(pts)
    if pts > 0:
        pts_text = f"+{pts_text}"
    return f"№{number}{date_part} ({pts_text})"
