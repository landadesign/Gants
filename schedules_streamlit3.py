import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
import datetime
import io
import time
import plotly.graph_objects as go
import matplotlib.font_manager as fm
import jpholiday
import os
import subprocess

# ページ設定を最初に行う
st.set_page_config(layout="wide")

# フォントの設定
def setup_japanese_fonts():
    try:
        # 基本的なフォント設定
        plt.rcParams['font.family'] = 'IPAGothic'  # IPAGothicを使用
        plt.rcParams['axes.unicode_minus'] = False  # マイナス記号の文字化け防止
        
        # フォントサイズの設定
        plt.rcParams['font.size'] = 9
        plt.rcParams['axes.labelsize'] = 9
        plt.rcParams['xtick.labelsize'] = 8
        plt.rcParams['ytick.labelsize'] = 8
        
    except Exception as e:
        st.warning(f"フォント設定中にエラーが発生しました: {str(e)}")

# フォントのセットアップを実行
setup_japanese_fonts()

# フォントプロパティの設定
jp_font = mpl.font_manager.FontProperties(family='Noto Sans CJK JP')

# ======== ヒラギノ角ゴシックの設定 (Hiragino Sans) ========
jp_font_path = None
for font_path in fm.findSystemFonts():
    if "Hiragino Sans" in font_path or "ヒラギノ角ゴ" in font_path:
        jp_font_path = font_path
        break

if jp_font_path:
    print(f"使用する日本語フォント: {jp_font_path}")
    jp_font = fm.FontProperties(fname=jp_font_path, size=7)
else:
    # フォールバックフォントの設定
    print("Hiragino Sans が見つかりません。MS Gothic を使用します。")
    jp_font = fm.FontProperties(family='MS Gothic', size=7)

# フォントの設定をmatplotlibのデフォルトに設定
plt.rcParams['font.family'] = 'IPAexGothic'

# ======== タスクの並行/連続をどう扱うか設定 ========
PARALLEL_TASKS = ["構造計算", "省エネ計算", "申請書類作成", "チェック", "修正"]
SEQUENTIAL_TASKS = ["提出", "事前審査", "訂正", "最終審査", "申請済予定"]

# タスクの種類に応じた色の定義
TASK_COLORS = {
    "着手日": "lightgreen",
    "設計図書作成": "skyblue",
    "parallel": "lightblue",  # 並行タスク用
    "sequential": "pink",     # 連続タスク用
    "default": "skyblue"      # その他のタスク用
}

# バーの色を決定する関数
def get_task_color(task, df):
    if task == "着手日":
        return "lightgreen"
    elif task in PARALLEL_TASKS or task in ["設計図書作成", "申請書類作成", "チェック", "修正"]:
        return "skyblue"
    elif task in SEQUENTIAL_TASKS:
        return "lightpink"
    else:
        # 追加タスクの場合、前後のタスクの色を確認して合わせる
        task_idx = df[df["Task"] == task].index[0]
        if task_idx > 0:
            prev_task = df.at[task_idx - 1, "Task"]
            if prev_task in SEQUENTIAL_TASKS:
                return "lightpink"
        if task_idx < len(df) - 1:
            next_task = df.at[task_idx + 1, "Task"]
            if next_task in SEQUENTIAL_TASKS:
                return "lightpink"
        return "skyblue"  # デフォルトは青系

def is_workday(date: pd.Timestamp) -> bool:
    """平日かつ祝日でないか"""
    return (date.weekday() < 5) and (not jpholiday.is_holiday(date))

def add_workdays(start_date: pd.Timestamp, workdays: int) -> pd.Timestamp:
    """
    start_date から 'workdays' 分だけ「平日のみ」進め、最終日を返す。
    (土日祝はスキップ)
    """
    current = start_date
    count = 0
    while count < workdays:
        current += pd.Timedelta(days=1)
        if is_workday(current):
            count += 1
    return current

def diff_workdays(start_date: pd.Timestamp, end_date: pd.Timestamp) -> int:
    """start_date ～ end_date の平日数をカウント"""
    if end_date < start_date:
        return 0
    d = start_date
    wcount = 0
    while d < end_date:
        d += pd.Timedelta(days=1)
        if is_workday(d):
            wcount += 1
    return wcount

def create_gantt_chart(tasks, durations, start_date, end_date, include_title=True):
    try:
        fig, ax = plt.subplots(figsize=(10, 6), dpi=200)
        
        # 基本的なレイアウト設定
        plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.2)
        
        # テキスト描画時のフォント指定を削除
        for i, (task, duration) in enumerate(zip(tasks, durations)):
            # ... 既存のコード ...
            ax.text(bar_center, y_positions[i], task_text,
                   va='center', ha='center',
                   color='black', fontsize=7)
        
        return fig
        
    except Exception as e:
        st.error(f"チャート作成中にエラーが発生しました: {str(e)}")
        raise e

def update_metrics(start_date, end_date):
    """メトリクスを更新する関数"""
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    available = diff_workdays(start, end)
    current_total = sum(st.session_state.durations.values())
    difference = available - current_total
    
    st.session_state.metrics = {
        'available_workdays': available,
        'current_total_days': current_total,
        'days_difference': difference
    }

def main():
    setup_japanese_fonts()
    # 日付の初期化
    today = datetime.date.today()
    default_end = today + datetime.timedelta(days=60)
    end_date = default_end

    # セッションステートの初期化
    if 'durations' not in st.session_state:
        st.session_state.durations = {
            "着手日": 1,
            "事前協議": 3,
            "設計図書作成": 7,
            "構造計算": 4,
            "省エネ計算": 4,
            "申請書類作成": 4,
            "チェック": 2,
            "修正": 2,
            "提出": 1,
            "事前審査": 9,
            "訂正": 2,
            "最終審査": 3,
            "申請済予定": 1
        }

    if 'metrics' not in st.session_state:
        st.session_state.metrics = {
            'available_workdays': 0,
            'current_total_days': 0,
            'days_difference': 0
        }

    # 最小値の設定（基本日数の半分、最小1日）
    min_durations = {task: max(1, st.session_state.durations[task] // 2) for task in st.session_state.durations.keys()}
    # 最大値の設定（基本日数の2倍）
    max_durations = {task: st.session_state.durations[task] * 2 for task in st.session_state.durations.keys()}

    # 13列のレイアウト
    cols = st.columns(13)

    # タスクリスト
    tasks = list(st.session_state.durations.keys())

    # カスタムCSS
    st.markdown("""
        <style>
        /* タスクコンテナのスタイル */
        .task-container {
            padding: 5px 10px;
            margin-bottom: 5px;
            text-align: center;
            border-radius: 4px;
        }
        
        /* タスク名のスタイル */
        .task-name {
            font-size: 16px;
            margin-bottom: 8px;
            line-height: 1.2;
        }

        /* 着手日のスタイル */
        .task-start {
            background-color: rgba(0, 100, 0, 0.1);
        }
        .task-start .task-name {
            color: #006400;
        }
        /* 着手日の入力フィールドのコンテナ幅を調整 */
        .task-start .stDateInput {
            margin-top: 18px !important;
            width: 70% !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        .task-start .stDateInput > div {
            width: 100% !important;
        }
        .task-start .stDateInput > div > div {
            border-color: #006400 !important;
            background-color: #00640033 !important;
            width: 100% !important;
        }
        .task-start .stDateInput input {
            color: #006400 !important;
            font-weight: bold !important;
            width: 100% !important;
        }
        .task-start .stDateInput svg {
            fill: #006400 !important;
        }

        /* 設計関連タスクのスタイル */
        .task-design {
            background-color: rgba(0, 0, 255, 0.1);
        }
        .task-design .task-name {
            color: #0000CD;
        }
        .task-design .stButton button {
            background-color: #0000FF;
            border-color: #0000FF;
            color: white;
            font-weight: bold;
        }
        .task-design .stButton button:hover {
            background-color: #0000CD;
            border-color: #0000CD;
        }

        /* 審査関連タスクのスタイル */
        .task-review {
            background-color: rgba(255, 0, 0, 0.1);
        }
        .task-review .task-name {
            color: #8B0000;
        }
        .task-review .stButton button {
            background-color: #FF0000;
            border-color: #FF0000;
            color: white;
            font-weight: bold;
        }
        .task-review .stButton button:hover {
            background-color: #CC0000;
            border-color: #CC0000;
        }

        /* ボタンの文字を太く */
        .stButton button {
            font-weight: bold !important;
        }

        /* ... rest of the styles ... */
        </style>
    """, unsafe_allow_html=True)
    
    # タスクの種類に応じてクラスを割り当て
    task_classes = {
        "着手日": "task-start",
        "事前協議": "task-design",
        "設計図書作成": "task-design",
        "構造計算": "task-design",
        "省エネ計算": "task-design",
        "申請書類作成": "task-design",
        "チェック": "task-design",
        "修正": "task-design",
        "提出": "task-review",
        "事前審査": "task-review",
        "訂正": "task-review",
        "最終審査": "task-review",
        "申請済予定": "task-review",
    }
    
    # タスクの表示
    for i, task in enumerate(tasks):
        with cols[i]:
            st.markdown(f'<div class="task-container {task_classes[task]}">', unsafe_allow_html=True)
            
            # タスク名の表示
            display_label = {
                "設計図書作成": "設計図書",
                "申請書類作成": "申請書類",
            }.get(task, task)
            st.markdown(f'<div class="task-name">{display_label}</div>', unsafe_allow_html=True)
            
            # 着手日は日付入力のみ
            if task == "着手日":
                start_date = st.date_input(
                    "",
                    value=today,
                    min_value=datetime.date(2024, 1, 1),
                    max_value=datetime.date(2030, 12, 31),
                    key="start_date",
                    format="YYYY/MM/DD",
                    label_visibility="collapsed"
                )
            else:
                # ボタングループを1つのコンテナにまとめる
                st.markdown('<div class="button-container">', unsafe_allow_html=True)
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    if st.button("−", key=f"minus_{task}"):
                        if st.session_state.durations[task] > 1:
                            st.session_state.durations[task] -= 1
                            st.rerun()
                
                with col2:
                    if st.button("＋", key=f"plus_{task}"):
                        st.session_state.durations[task] += 1
                        st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown('</div>', unsafe_allow_html=True)

    # 間隔を狭くするためのスペース調整
    st.markdown('<div style="margin-top: -25px;"></div>', unsafe_allow_html=True)
    
    # 表示用のガントチャート（タイトルなし）
    display_fig = create_gantt_chart(tasks, st.session_state.durations, start_date, end_date, include_title=False)
    
    # ガントチャートを表示
    st.pyplot(display_fig)
    plt.close(display_fig)
    
    # 保存用のガントチャート（タイトル付き）
    save_fig = create_gantt_chart(tasks, st.session_state.durations, start_date, end_date, include_title=True)
    
    # 画像保存用のバッファを作成
    buffer = io.BytesIO()
    save_fig.savefig(buffer, format='png', dpi=200, bbox_inches='tight')
    buffer.seek(0)
    plt.close(save_fig)
    
    # ダウンロードボタンのスタイル
    st.markdown("""
        <style>
        .stDownloadButton button {
            background-color: #1f77b4;
            color: white;
            border: 1px solid #1f77b4;
            border-radius: 16px;
            padding: 4px 15px;
            font-size: 14px;
        }
        .stDownloadButton button:hover {
            background-color: #1565c0;
            border-color: #1565c0;
        }
        /* ボタンを右寄せにする */
        .stDownloadButton {
            display: flex;
            justify-content: flex-end;
            margin-right: 20px;
            margin-top: -20px;  /* ガントチャートとの間隔を調整 */
        }
        </style>
    """, unsafe_allow_html=True)
    
    # ダウンロードボタンを配置
    col1, col2 = st.columns([6, 1])
    with col2:
        st.download_button(
            label="画像保存",
            data=buffer,
            file_name="申請スケジュール.png",
            mime="image/png",
            key="download_button"
        )

    # タスク数のデータを作成
    task_counts = st.session_state.durations
    
    # ガントチャートのデータ作成
    fig = go.Figure()
    
    for i, (task_name, count) in enumerate(task_counts.items()):
        fig.add_trace(go.Bar(
            y=[task_name],
            x=[count],
            orientation='h',
            text=f'{count}',
            textposition='inside',
            textfont=dict(
                size=14,
                color='white'
            ),
            marker=dict(color='#1f77b4'),
            showlegend=False
        ))

    # グラフのレイアウト設定
    fig.update_layout(
        height=200,
        margin=dict(l=0, r=0, t=0, b=0),
        yaxis=dict(
            showgrid=False,
            zeroline=False
        ),
        xaxis=dict(
            showgrid=True,
            zeroline=False
        )
    )

if __name__ == "__main__":
    main()
