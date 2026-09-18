"""Правила нарахування балів за наказами про подяки та догани."""


def format_points(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return str(int(number))
    return f"{number:g}"


def displayed_total(raw_total):
    """Підсумок для таблиці рейтингу: догани враховуються, але не нижче нуля."""
    try:
        return max(0.0, float(raw_total or 0))
    except (TypeError, ValueError):
        return 0.0


def applied_points(order_kind, configured_points, current_total=0):
    """Фактична зміна, яку записуємо в нарахування.

    Подяка: +configured_points.
    Догана: завжди −configured_points (навіть якщо зараз 0), щоб пізніша
    подяка «перекрила» догану: −0.5 + 1 = 0.5. Від’ємний підсумок
    на екрані ховається через displayed_total().
    """
    del current_total  # лишається в сигнатурі для сумісності викликів
    points = abs(float(configured_points))
    if order_kind == "reprimand":
        return -points
    return points


def format_achievement_line(item):
    """Короткий рядок: «№12 від 01.09.2026 (+1)»."""
    number = item.get("order_number") or "Б/Н"
    date = item.get("order_date") or ""
    pts = float(item.get("points") or 0)
    pts_text = format_points(pts)
    if pts > 0:
        pts_text = f"+{pts_text}"
    date_part = f" від {date}" if date and date != "Не вказана" else ""
    
    # Якщо є змішані типи, показуємо просто "змішані"
    if "commendation_types" in item and len(item["commendation_types"]) > 1:
        return f"№{number}{date_part} (змішані, {pts_text})"
    
    return f"№{number}{date_part} ({pts_text})"
