"""Правила нарахування балів за наказами про подяки та догани."""


def format_points(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number):
        return str(int(number))
    return f"{number:g}"


def applied_points(order_kind, configured_points, current_total=0):
    """Повертає фактичну зміну рейтингу для одного студента.

    Подяка: завжди додає configured_points.
    Догана: якщо поточний рейтинг 0 або менше — бали не чіпаємо;
    якщо є бали — віднімаємо configured_points, але не нижче нуля.
    """
    points = abs(float(configured_points))
    if order_kind != "reprimand":
        return points

    current = float(current_total or 0)
    if current <= 0:
        return 0.0
    return -min(points, current)
