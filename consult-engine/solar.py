"""真太阳时校正(排盘根基;DESIGN §5 分级承诺)。

时辰应按出生地的**真太阳时**判定,而非北京钟表时间:
  真太阳时 = 钟表时(标准时) + 经度差 + 均时差
  - 经度差:(出生地经度 − 120°E) × 4 分钟/度(兰州约 −65 分钟,乌鲁木齐约 −130 分钟)
  - 均时差(equation of time):地球轨道偏心+黄赤交角造成的季节性 ±16 分钟,NOAA 简化式(精度约 ±20 秒)

纯标准库、确定性。经度缺省(None)= 不校正,行为与旧版完全一致。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

_TZ8 = timezone(timedelta(hours=8))


def equation_of_time_minutes(t_unix: int) -> float:
    """均时差(分钟,NOAA 简化式);正值 = 真太阳时快于平太阳时。"""
    n = datetime.fromtimestamp(t_unix, _TZ8).timetuple().tm_yday
    b = 2.0 * math.pi * (n - 81) / 364.0
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def true_solar_offset_seconds(longitude: float, t_unix: int) -> int:
    """出生地经度 → 相对北京标准时(120°E)的真太阳时偏移(秒)。"""
    lon_sec = (longitude - 120.0) * 240.0          # 每度 4 分钟
    eot_sec = equation_of_time_minutes(t_unix) * 60.0
    return round(lon_sec + eot_sec)


# 常用城市经度(排盘校正用;取市区代表值,精度 0.1° ≈ 24 秒,足够时辰判定)
CITY_LONGITUDE = {
    "北京": 116.4, "天津": 117.2, "上海": 121.5, "重庆": 106.6,
    "广州": 113.3, "深圳": 114.1, "杭州": 120.2, "南京": 118.8,
    "苏州": 120.6, "武汉": 114.3, "成都": 104.1, "西安": 108.9,
    "郑州": 113.6, "长沙": 112.9, "合肥": 117.2, "南昌": 115.9,
    "福州": 119.3, "厦门": 118.1, "济南": 117.1, "青岛": 120.4,
    "石家庄": 114.5, "太原": 112.6, "沈阳": 123.4, "大连": 121.6,
    "长春": 125.3, "哈尔滨": 126.5, "昆明": 102.8, "贵阳": 106.6,
    "南宁": 108.4, "海口": 110.3, "兰州": 103.8, "西宁": 101.8,
    "银川": 106.2, "乌鲁木齐": 87.6, "拉萨": 91.1, "呼和浩特": 111.7,
    "香港": 114.2, "澳门": 113.5, "台北": 121.5,
}
