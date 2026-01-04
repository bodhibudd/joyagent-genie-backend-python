from datetime import date

def time_info() -> str:
    today = date.today()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    day_of_week = weekdays[today.weekday()]
    current_date_info = f"今天是 {today.strftime('%Y年%m月%d日')}，{day_of_week}"

    return current_date_info
