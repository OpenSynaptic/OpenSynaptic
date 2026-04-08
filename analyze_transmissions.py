"""
OpenSynaptic 传输数据分析工具
用法:
  pip install streamlit plotly pandas
  streamlit run analyze_transmissions.py
"""
from __future__ import annotations
import sys, json, time, random
from pathlib import Path

# ── 生成测试传输数据 ────────────────────────────────────────────────────────
def _generate_sample_data(n: int = 200) -> list[dict]:
    """
    如果没有 SQL 数据库，生成一批仿真传输记录用于演示。
    每条记录对应一次 transmit() 调用的结果。
    """
    devices = ["HUB_01", "DEMO_NODE", "SENSOR_A", "FIELD_03"]
    units_pool = [
        ("TMP", "temperature"), ("PRS", "pressure"),
        ("HUM", "humidity"),    ("CUR", "electric_current"),
    ]
    strategies = ["FULL_PACKET", "DIFF_PACKET"]
    rows = []
    base_ts = int(time.time()) - n * 3

    for i in range(n):
        device = random.choice(devices)
        ts = base_ts + i * 3 + random.randint(0, 2)
        num_sensors = random.randint(1, 5)

        # 模拟传感器读数（带漂移噪声）
        sensors = []
        for j in range(num_sensors):
            sid, unit = random.choice(units_pool)
            base_vals = {"temperature": 25.0, "pressure": 101325.0,
                         "humidity": 55.0, "electric_current": 2.5}
            noise = random.gauss(0, base_vals[unit] * 0.03)
            sensors.append({
                "sensor_id": f"{sid}{j}",
                "normalized_value": round(base_vals[unit] + noise, 4),
                "normalized_unit": unit,
                "status": "OK" if random.random() > 0.05 else "ERR",
            })

        raw_bytes = random.randint(60, 200)
        strategy = random.choices(strategies, weights=[0.3, 0.7])[0]
        compressed = raw_bytes if strategy == "FULL_PACKET" else int(raw_bytes * random.uniform(0.2, 0.6))

        rows.append({
            "device_id": device,
            "device_status": "ONLINE" if random.random() > 0.08 else "OFFLINE",
            "timestamp": ts,
            "strategy": strategy,
            "raw_bytes": raw_bytes,
            "compressed_bytes": compressed,
            "stage_standardize_ms": round(random.uniform(0.008, 0.025), 4),
            "stage_compress_ms": round(random.uniform(0.01, 0.12), 4),
            "stage_fuse_ms": round(random.uniform(0.03, 2.0), 4),
            "sensors": sensors,
        })
    return rows


def _load_from_sqlite(db_path: Path) -> list[dict]:
    """从 SQLite 数据库读取真实传输记录。"""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    packets = cur.execute(
        "SELECT * FROM os_packets ORDER BY timestamp_raw DESC LIMIT 2000"
    ).fetchall()
    result = []
    for p in packets:
        sensors = cur.execute(
            "SELECT * FROM os_sensors WHERE packet_uuid=?", (p["packet_uuid"],)
        ).fetchall()
        result.append({
            "device_id": p["device_id"],
            "device_status": p["device_status"],
            "timestamp": p["timestamp_raw"],
            "strategy": json.loads(p["payload_json"] or "{}").get("strategy", "FULL_PACKET"),
            "raw_bytes": 0,
            "compressed_bytes": 0,
            "stage_standardize_ms": 0,
            "stage_compress_ms": 0,
            "stage_fuse_ms": 0,
            "sensors": [
                {
                    "sensor_id": s["sensor_id"],
                    "normalized_value": s["normalized_value"],
                    "normalized_unit": s["normalized_unit"],
                    "status": s["sensor_status"],
                }
                for s in sensors
            ],
        })
    conn.close()
    return result


# ── 主 Streamlit 应用 ───────────────────────────────────────────────────────
def main():
    import streamlit as st
    import plotly.express as px
    import plotly.graph_objects as go
    import pandas as pd

    st.set_page_config(
        page_title="OpenSynaptic 传输数据分析",
        page_icon="📡",
        layout="wide",
    )
    st.title("📡 OpenSynaptic 传输数据分析")

    # 数据源选择
    db_path = Path("data/opensynaptic.db")
    if db_path.exists():
        records = _load_from_sqlite(db_path)
        st.success(f"从 SQLite 加载了 {len(records)} 条真实传输记录")
    else:
        records = _generate_sample_data(200)
        st.info("未找到 data/opensynaptic.db，使用模拟数据（200 条）。"
                "在 Config.json 里开启 SQL 即可用真实数据。")

    if not records:
        st.error("无数据")
        return

    # 展平为 DataFrame
    df_pkts = pd.DataFrame([
        {k: v for k, v in r.items() if k != "sensors"} for r in records
    ])
    df_pkts["timestamp"] = pd.to_datetime(df_pkts["timestamp"], unit="s")
    df_pkts["total_stage_ms"] = (
        df_pkts["stage_standardize_ms"] +
        df_pkts["stage_compress_ms"] +
        df_pkts["stage_fuse_ms"]
    )
    df_pkts["compression_ratio"] = (
        df_pkts["compressed_bytes"] / df_pkts["raw_bytes"].replace(0, 1)
    ).round(3)

    df_sensors = pd.DataFrame([
        {**s, "device_id": r["device_id"], "timestamp": pd.Timestamp(r["timestamp"], unit="s")}
        for r in records for s in r["sensors"]
    ])

    # ── 顶部指标卡片 ──────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("总包数", len(df_pkts))
    c2.metric("设备数", df_pkts["device_id"].nunique())
    c3.metric("DIFF 包占比",
              f"{(df_pkts['strategy']=='DIFF_PACKET').mean()*100:.1f}%")
    c4.metric("平均压缩率",
              f"{df_pkts['compression_ratio'].mean():.2f}x" if df_pkts["raw_bytes"].sum() > 0 else "N/A")
    c5.metric("平均 Pipeline ms",
              f"{df_pkts['total_stage_ms'].mean():.3f}")

    st.divider()

    # ── Tab 布局 ──────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 传感器趋势", "📦 包分析", "⏱ Pipeline 耗时", "🔧 设备状态"]
    )

    # ── Tab1：传感器值趋势 ────────────────────────────────────────────────
    with tab1:
        st.subheader("传感器读数趋势")
        if df_sensors.empty:
            st.warning("无传感器数据")
        else:
            units = df_sensors["normalized_unit"].unique().tolist()
            selected_unit = st.selectbox("选择物理量", units)
            selected_devices = st.multiselect(
                "选择设备", df_sensors["device_id"].unique().tolist(),
                default=df_sensors["device_id"].unique().tolist()[:2]
            )
            dff = df_sensors[
                (df_sensors["normalized_unit"] == selected_unit) &
                (df_sensors["device_id"].isin(selected_devices))
            ].sort_values("timestamp")

            if not dff.empty:
                fig = px.line(
                    dff, x="timestamp", y="normalized_value",
                    color="device_id", line_group="sensor_id",
                    title=f"{selected_unit} 传感器读数随时间变化",
                    labels={"normalized_value": selected_unit, "timestamp": "时间"},
                    template="plotly_dark",
                )
                fig.update_traces(mode="lines+markers", marker_size=4)
                st.plotly_chart(fig, use_container_width=True)

            # 各物理量数据量分布
            unit_counts = df_sensors["normalized_unit"].value_counts().reset_index()
            unit_counts.columns = ["unit", "count"]
            fig2 = px.bar(unit_counts, x="unit", y="count",
                          title="各物理量传感器读数数量",
                          color="unit", template="plotly_dark")
            st.plotly_chart(fig2, use_container_width=True)

    # ── Tab2：包分析 ─────────────────────────────────────────────────────
    with tab2:
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("FULL vs DIFF 包分布")
            strat_counts = df_pkts["strategy"].value_counts().reset_index()
            strat_counts.columns = ["strategy", "count"]
            fig3 = px.pie(strat_counts, names="strategy", values="count",
                          color_discrete_map={
                              "FULL_PACKET": "#e74c3c",
                              "DIFF_PACKET": "#2ecc71"
                          },
                          template="plotly_dark")
            st.plotly_chart(fig3, use_container_width=True)

        with col_b:
            st.subheader("压缩率分布（DIFF 包）")
            diff_df = df_pkts[df_pkts["strategy"] == "DIFF_PACKET"]
            if not diff_df.empty and diff_df["raw_bytes"].sum() > 0:
                fig4 = px.histogram(
                    diff_df, x="compression_ratio", nbins=20,
                    title="DIFF 包压缩率直方图",
                    labels={"compression_ratio": "压缩后/原始字节比"},
                    template="plotly_dark", color_discrete_sequence=["#3498db"]
                )
                st.plotly_chart(fig4, use_container_width=True)
            else:
                st.info("无压缩字节数据（需真实 SQL 数据）")

        # 包频率时间线
        st.subheader("每分钟包传输频率（按设备）")
        df_pkts["minute"] = df_pkts["timestamp"].dt.floor("min")
        freq = df_pkts.groupby(["minute", "device_id"]).size().reset_index(name="count")
        fig5 = px.area(freq, x="minute", y="count", color="device_id",
                       title="传输频率（包/分钟）",
                       template="plotly_dark")
        st.plotly_chart(fig5, use_container_width=True)

    # ── Tab3：Pipeline 耗时 ───────────────────────────────────────────────
    with tab3:
        st.subheader("Pipeline 各阶段耗时")
        if df_pkts["total_stage_ms"].sum() == 0:
            st.info("stage 耗时仅在真实传输数据中可用")
        else:
            # 按设备分组堆叠柱图
            stage_df = df_pkts.melt(
                id_vars=["device_id", "timestamp"],
                value_vars=["stage_standardize_ms", "stage_compress_ms", "stage_fuse_ms"],
                var_name="stage", value_name="ms"
            )
            stage_df["stage"] = stage_df["stage"].str.replace("stage_", "").str.replace("_ms", "")
            fig6 = px.box(stage_df, x="stage", y="ms", color="stage",
                          title="各 Stage 耗时分布（Box Plot）",
                          template="plotly_dark",
                          color_discrete_map={
                              "standardize": "#3498db",
                              "compress": "#2ecc71",
                              "fuse": "#e74c3c"
                          })
            st.plotly_chart(fig6, use_container_width=True)

            # 散点：fuse 耗时 vs 传感器数量
            sensor_counts = pd.Series(
                {i: len(r["sensors"]) for i, r in enumerate(records)},
                name="sensor_count"
            )
            df_scatter = df_pkts.copy().reset_index()
            df_scatter["sensor_count"] = sensor_counts.values
            fig7 = px.scatter(
                df_scatter, x="sensor_count", y="stage_fuse_ms",
                color="strategy", trendline="ols",
                title="传感器数量 vs Fuse 耗时",
                labels={"sensor_count": "传感器数量", "stage_fuse_ms": "fuse 耗时 (ms)"},
                template="plotly_dark"
            )
            st.plotly_chart(fig7, use_container_width=True)

    # ── Tab4：设备状态 ───────────────────────────────────────────────────
    with tab4:
        st.subheader("设备在线/离线时间轴")
        timeline_data = []
        for device, grp in df_pkts.groupby("device_id"):
            grp = grp.sort_values("timestamp")
            for _, row in grp.iterrows():
                timeline_data.append({
                    "Device": device,
                    "Start": row["timestamp"],
                    "Finish": row["timestamp"] + pd.Timedelta(seconds=3),
                    "Status": row["device_status"],
                })
        if timeline_data:
            tdf = pd.DataFrame(timeline_data)
            fig8 = px.timeline(
                tdf, x_start="Start", x_end="Finish", y="Device",
                color="Status",
                color_discrete_map={"ONLINE": "#2ecc71", "OFFLINE": "#e74c3c"},
                title="设备在线状态时间轴",
                template="plotly_dark"
            )
            st.plotly_chart(fig8, use_container_width=True)

        # 每设备传输统计表
        st.subheader("设备传输统计汇总")
        summary = df_pkts.groupby("device_id").agg(
            总包数=("strategy", "count"),
            DIFF包数=("strategy", lambda x: (x == "DIFF_PACKET").sum()),
            离线次数=("device_status", lambda x: (x == "OFFLINE").sum()),
            平均Pipeline_ms=("total_stage_ms", "mean"),
        ).round(4)
        summary["DIFF占比%"] = (summary["DIFF包数"] / summary["总包数"] * 100).round(1)
        st.dataframe(summary, use_container_width=True)


if __name__ == "__main__":
    # 若直接 python 运行，打印数据摘要
    records = _generate_sample_data(50)
    import json as _json
    print(f"Sample: {len(records)} records")
    print(_json.dumps(records[0], indent=2, default=str))
