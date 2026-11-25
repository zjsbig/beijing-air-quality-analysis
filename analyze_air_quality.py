# -*- coding: utf-8 -*-
"""
项目一：北京空气质量数据采集与分析
数据来源：Open-Meteo 免费公开数据接口（不需要注册、不需要密钥）
运行方式：双击同目录下的 run.bat，或在命令行执行 python analyze_air_quality.py

作者：张嘉硕
"""

import os
import time
import datetime as dt
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # 不弹窗，直接把图片保存成文件
import matplotlib.pyplot as plt

# ==================== 0. 基础设置 ====================
LAT, LON = 39.9042, 116.4074   # 北京的经纬度
DAYS = 90                      # 采集最近 90 天

# 气象历史接口有约 5 天延迟，所以窗口截止到 5 天前，保证两类数据日期完全对齐
END_DATE = dt.date.today() - dt.timedelta(days=5)
START_DATE = END_DATE - dt.timedelta(days=DAYS - 1)

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
CHART_DIR = os.path.join(BASE, "charts")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CHART_DIR, exist_ok=True)

# 让图表里的中文正常显示
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_json(url, params):
    """调用公开接口，返回 JSON 数据（失败自动重试 3 次）"""
    last_err = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            print(f"  第 {attempt} 次请求失败（{type(e).__name__}），稍后重试……")
            time.sleep(attempt * 3)
    raise RuntimeError(f"数据接口访问失败，请检查网络后重试：{last_err}")


# ==================== 1. 采集数据 ====================
print(f"第 1 步：采集空气质量数据（{START_DATE} 至 {END_DATE}）……")
air = fetch_json(
    "https://air-quality-api.open-meteo.com/v1/air-quality",
    {
        "latitude": LAT,
        "longitude": LON,
        "hourly": "pm2_5,pm10,ozone,nitrogen_dioxide",
        "start_date": str(START_DATE),
        "end_date": str(END_DATE),
        "timezone": "Asia/Shanghai",
    },
)

print("第 2 步：采集气象数据（历史接口）……")
weather = fetch_json(
    "https://archive-api.open-meteo.com/v1/archive",
    {
        "latitude": LAT,
        "longitude": LON,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "start_date": str(START_DATE),
        "end_date": str(END_DATE),
        "timezone": "Asia/Shanghai",
    },
)

# ==================== 2. 整理成表格 ====================
df = pd.merge(
    pd.DataFrame(air["hourly"]),
    pd.DataFrame(weather["hourly"]),
    on="time",
    how="inner",
)
df = df.rename(
    columns={
        "time": "时间",
        "pm2_5": "PM2.5",
        "pm10": "PM10",
        "ozone": "臭氧",
        "nitrogen_dioxide": "二氧化氮",
        "temperature_2m": "气温",
        "relative_humidity_2m": "相对湿度",
        "wind_speed_10m": "风速",
    }
)
df["时间"] = pd.to_datetime(df["时间"])
df = df.sort_values("时间").reset_index(drop=True)
raw_count = len(df)
print(f"采集完成：原始数据 {raw_count} 条")

# ==================== 3. 数据清洗 ====================
df = df.dropna(subset=["PM2.5"])                       # 删掉 PM2.5 缺失的行
for col in ["PM10", "臭氧", "二氧化氮", "气温", "相对湿度", "风速"]:
    df[col] = df[col].interpolate(limit_direction="both")   # 线性插值补全
for col in ["PM2.5", "PM10", "臭氧", "二氧化氮", "风速"]:
    df = df[df[col] >= 0]                              # 去掉负数
for col in ["PM2.5", "PM10"]:
    low, high = df[col].quantile(0.01), df[col].quantile(0.99)
    df[col] = df[col].clip(low, high)                  # 极端值截断
df = df.reset_index(drop=True)
clean_count = len(df)
print(f"清洗完成：保留 {clean_count} 条，删除 {raw_count - clean_count} 条")

# 增加日期、月份、小时、是否周末等分析字段
df["日期"] = df["时间"].dt.date
df["月份"] = df["时间"].dt.month
df["小时"] = df["时间"].dt.hour
df["是否周末"] = df["时间"].dt.day_of_week >= 5

csv_path = os.path.join(DATA_DIR, "beijing_air_clean.csv")
df.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"清洗后的数据已保存：{csv_path}")

# ==================== 4. 统计分析 ====================
pm_mean = df["PM2.5"].mean()
pm_max = df["PM2.5"].max()
max_row = df.loc[df["PM2.5"].idxmax()]
monthly = df.groupby("月份")["PM2.5"].mean().round(1)
hourly = df.groupby("小时")["PM2.5"].mean()
peak_hour = hourly.idxmax()
corr = df[["PM2.5", "气温", "相对湿度", "风速"]].corr()["PM2.5"].drop("PM2.5").round(2)
weekend = df.groupby("是否周末")["PM2.5"].mean()

print("\n========== 分析结果 ==========")
print(f"PM2.5 平均浓度：{pm_mean:.1f} 微克/立方米")
print(f"PM2.5 最高值：{pm_max:.1f}（出现在 {max_row['时间']}）")
print("各月平均浓度：")
print(monthly.to_string())
print(f"一天中平均浓度最高的是 {peak_hour} 点（{hourly.max():.1f}）")
print("与 PM2.5 的相关系数（负数表示该值越高、污染越轻）：")
print(corr.to_string())
print("工作日 / 周末平均浓度：")
print(weekend.round(1).to_string())

# ==================== 5. 可视化 ====================
def save_chart(fig, name):
    path = os.path.join(CHART_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"图表已保存：{path}")


# 图 1：PM2.5 随时间变化
fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(df["时间"], df["PM2.5"], linewidth=0.8, color="#2b6cb0")
ax.set_title(f"PM2.5 逐小时变化（{START_DATE} 至 {END_DATE}）")
ax.set_xlabel("时间")
ax.set_ylabel("PM2.5（微克/立方米）")
save_chart(fig, "01_PM25时间序列.png")

# 图 2：各月平均浓度
fig, ax = plt.subplots(figsize=(7, 4))
ax.bar(monthly.index.astype(str), monthly.values, color="#dd6b20")
ax.set_title("各月 PM2.5 平均浓度")
ax.set_xlabel("月份")
ax.set_ylabel("PM2.5 平均浓度（微克/立方米）")
save_chart(fig, "02_各月平均浓度.png")

# 图 3：一天 24 小时的变化规律
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(hourly.index, hourly.values, marker="o", color="#38a169")
ax.set_title("一天中不同时刻的 PM2.5 平均浓度")
ax.set_xlabel("小时")
ax.set_ylabel("PM2.5 平均浓度（微克/立方米）")
ax.set_xticks(range(0, 24, 2))
save_chart(fig, "03_逐小时变化.png")

# 图 4：风速与 PM2.5 的关系
fig, ax = plt.subplots(figsize=(6, 4))
ax.scatter(df["风速"], df["PM2.5"], s=8, alpha=0.5, color="#805ad5")
ax.set_title(f"风速与 PM2.5 的关系（相关系数 {corr['风速']}）")
ax.set_xlabel("风速（米/秒）")
ax.set_ylabel("PM2.5（微克/立方米）")
save_chart(fig, "04_风速相关性.png")

# ==================== 6. 自动生成分析报告 ====================
month_text = "、".join([f"{m} 月 {v:.1f}" for m, v in monthly.items()])
workday_val = weekend.get(False, float("nan"))
rest_val = weekend.get(True, float("nan"))

report = f"""# 北京空气质量数据分析报告

- 数据来源：Open-Meteo 公开数据接口
- 采集范围：北京 {START_DATE} 至 {END_DATE}（{DAYS} 天）逐小时数据
- 分析时间：{pd.Timestamp.now():%Y-%m-%d}

## 一、数据概况

- 原始数据 {raw_count} 条，清洗后保留 {clean_count} 条
- PM2.5 平均浓度 {pm_mean:.1f} 微克/立方米，最高 {pm_max:.1f}
  （出现在 {max_row['时间']}）

## 二、主要发现

1. 各月 PM2.5 平均浓度：{month_text}
2. 一天中 {peak_hour} 点的平均浓度最高，为 {hourly.max():.1f} 微克/立方米
3. 与 PM2.5 的相关系数：气温 {corr['气温']}、相对湿度 {corr['相对湿度']}、风速 {corr['风速']}
4. 工作日平均 {workday_val:.1f}，周末平均 {rest_val:.1f}

## 三、结论

风速与 PM2.5 呈负相关，说明风速越大，污染物越容易被吹散；
相对湿度、气温与污染浓度的关系需要结合季节进一步分析。

## 四、图表

见 charts 文件夹中的四张图。
"""

report_path = os.path.join(BASE, "分析报告.md")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(report)
print(f"\n分析报告已生成：{report_path}")
print("\n全部完成！打开 charts 文件夹看图，打开 分析报告.md 看结论。")
