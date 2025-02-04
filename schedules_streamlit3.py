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
import japanize_matplotlib  # 日本語フォント対応のためのライブラリを追加

# ページ設定を最初に行う
st.set_page_config(layout="wide")

# フォントの設定
def setup_japanese_fonts():
    try:
        # 基本的なフォント設定
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
        df = pd.DataFrame({"Task": tasks})
        df["Workdays"] = df["Task"].apply(lambda x: durations[x])
        df["Start"] = pd.NaT
        df["End"] = pd.NaT

        current_date = pd.to_datetime(start_date)
        
        # まず着手日を処理
        start_idx = df[df["Task"] == "着手日"].index[0]
        df.at[start_idx, "Start"] = current_date
        df.at[start_idx, "End"] = add_workdays(current_date, df.at[start_idx, "Workdays"])
        current_date = df.at[start_idx, "End"]
        
        # 事前協議など、設計図書作成前のタスクを処理
        for i in range(len(df)):
            if i == start_idx:  # 着手日はスキップ
                continue
            task = df.at[i, "Task"]
            if task == "設計図書作成":
                break
            elif task not in PARALLEL_TASKS and task not in SEQUENTIAL_TASKS:
                df.at[i, "Start"] = current_date
                df.at[i, "End"] = add_workdays(current_date, df.at[i, "Workdays"])
                current_date = df.at[i, "End"]

        # 設計図書作成の処理
        design_idx = df[df["Task"] == "設計図書作成"].index[0]
        df.at[design_idx, "Start"] = current_date
        df.at[design_idx, "End"] = add_workdays(current_date, df.at[design_idx, "Workdays"])
        design_end = df.at[design_idx, "End"]

        # 設計図書作成と並行するタスク（および設計図書作成～修正の間のタスク）
        parallel_end = design_end
        for i in range(len(df)):
            task = df.at[i, "Task"]
            if pd.isna(df.at[i, "Start"]):  # まだスケジュールされていないタスク
                if task in PARALLEL_TASKS or task in ["申請書類作成", "チェック", "修正"]:
                    df.at[i, "End"] = parallel_end  # 終了日を設計図書作成に合わせる
                    needed = df.at[i, "Workdays"]
                    new_start = parallel_end
                    wcount = 0
                    while wcount < needed:
                        new_start -= pd.Timedelta(days=1)
                        if is_workday(new_start):
                            wcount += 1
                    df.at[i, "Start"] = new_start

        # 修正以降の連続タスク処理
        last_end = parallel_end
        for i, tname in enumerate(SEQUENTIAL_TASKS):
            seq_row = df[df["Task"] == tname]
            if seq_row.empty:
                continue
            seq_i = seq_row.index[0]
            
            # 開始日を設定（前のタスクの終了日）
            df.at[seq_i, "Start"] = last_end
            needed_days = df.at[seq_i, "Workdays"]
            
            # 作業可能日数をカウントしながら終了日を計算
            end_date = last_end
            work_days_count = 0
            
            # まず必要な作業日数分進める
            while work_days_count < needed_days:
                end_date += pd.Timedelta(days=1)
                if is_workday(end_date):
                    work_days_count += 1
            
            # 終了日が休日なら、前の平日まで戻る
            while not is_workday(end_date):
                end_date -= pd.Timedelta(days=1)
            
            # この時点で作業日数が足りているか確認
            actual_work_days = diff_workdays(last_end, end_date)
            if actual_work_days < needed_days:
                # 足りない場合、次の平日まで進める
                while actual_work_days < needed_days or not is_workday(end_date):
                    end_date += pd.Timedelta(days=1)
                    if is_workday(end_date):
                        actual_work_days += 1
            
            df.at[seq_i, "End"] = end_date
            last_end = end_date

        # 追加タスクの処理（設計図書作成〜修正の間以外）
        for i in range(len(df)):
            if pd.isna(df.at[i, "Start"]):
                task = df.at[i, "Task"]
                # 前のタスクの終了日を取得
                prev_end = df.iloc[i-1]["End"]
                # 次のタスクの開始日を取得
                next_start = None
                for j in range(i+1, len(df)):
                    if not pd.isna(df.at[j, "Start"]):
                        next_start = df.at[j, "Start"]
                        break
                
                if next_start is not None:
                    # 作業日数を取得
                    work_days = df.at[i, "Workdays"]
                    # 次のタスクの開始日から逆算して配置
                    end_date = next_start
                    start_date = end_date
                    for _ in range(work_days):
                        start_date -= pd.Timedelta(days=1)
                        while not is_workday(start_date):
                            start_date -= pd.Timedelta(days=1)
                    df.at[i, "Start"] = start_date
                    df.at[i, "End"] = end_date
                else:
                    # 次のタスクがない場合は前のタスクの後ろに配置
                    df.at[i, "Start"] = prev_end
                    df.at[i, "End"] = add_workdays(prev_end, df.at[i, "Workdays"])

        # 作業日数の合計を計算
        total_workdays = sum(durations.values())
        
        # グラフ作成
        fig, ax = plt.subplots(figsize=(10, 6), dpi=200)

        # フォントサイズを調整（バーの文字を半分に）
        plt.rcParams['font.size'] = 7         # 基本フォントサイズ
        plt.rcParams['axes.labelsize'] = 8    # 軸ラベルのフォントサイズ
        plt.rcParams['xtick.labelsize'] = 7   # X軸目盛りのフォントサイズ
        plt.rcParams['ytick.labelsize'] = 7   # Y軸目盛りのフォントサイズ
        
        # y軸の位置を定義
        y_positions = range(len(df))

        date_range = pd.date_range(start=df["Start"].min() - pd.Timedelta(days=3), 
                                  end=df["End"].max() + pd.Timedelta(days=3), 
                                  freq="D")
        
        # 1. 最背面に土日祝の背景を描画
        for d in date_range:
            if not is_workday(d):
                ax.axvspan(d.toordinal(), d.toordinal() + 1, color="lightgray", alpha=0.2, zorder=1)

        # 2. その上にタスクの背景色を描画
        for i in y_positions:
            if i % 2 == 0:
                ax.axhspan(i - 0.4, i + 0.4, color='#f0f8ff', alpha=0.3, zorder=2)

        # 3. 日付の縦線を描画
        for d in date_range:
            ax.axvline(d.toordinal(), color="lightgray", linestyle="--", linewidth=0.5, alpha=0.3, zorder=3)

        # 4. 最前面にバーを描画
        for i in range(len(df)):
            s = df.at[i, "Start"]
            e = df.at[i, "End"]
            if pd.notna(s) and pd.notna(e):
                # バーの描画（高さを大きく）
                bar = ax.barh(y_positions[i], (e - s).days + 1, left=s.toordinal(), 
                        color=get_task_color(df.at[i, "Task"], df),
                        alpha=0.8,
                        height=0.8,
                        zorder=4)
                
                # バーの中央にタスク名と日数を表示
                bar_width = (e - s).days + 1
                bar_center = s.toordinal() + bar_width / 2
                task_text = f'{df.at[i, "Task"]}\n({df.at[i, "Workdays"]}日)'
                ax.text(bar_center, y_positions[i], task_text,
                        va='center', ha='center',
                        color='black', fontsize=7, zorder=5)
                
                # 完了日をバーの最後尾からさらに後ろに表示
                ax.text(e.toordinal() + 1.0, y_positions[i],
                        e.strftime('%m-%d'),
                        va='center', ha='left',
                        color='black', fontsize=7, zorder=5)
                
                # 開始日をバーの下に表示
                ax.text(s.toordinal(), y_positions[i] - 0.3,
                        s.strftime('%m-%d'),
                        va='top', ha='left',
                        fontsize=7, zorder=5)

        # グリッド線の追加（最背面）
        ax.grid(True, axis='x', linestyle='--', alpha=0.3, zorder=0)

        ax.set_xlim(date_range[0].toordinal(), 
                   date_range[-1].toordinal() + 3)  # 右側の余白を増やす
        ax.set_xlabel("日付", fontproperties=jp_font, fontsize=8)
        ax.set_ylabel("タスク", fontproperties=jp_font, fontsize=8)
        
        # タイトルは保存時のみ表示（フォントサイズを小さく）
        if include_title:
            current_date = datetime.date.today().strftime('%Y/%m/%d')
            ax.set_title('申請スケジュール (総作業日数: {}日 作成日: {})'.format(
                total_workdays, current_date),
                pad=20, fontproperties=jp_font, fontsize=10)  # フォントサイズを12から10に変更

        ax.set_yticks([])
        ax.set_yticklabels([])

        # x軸の設定を5日単位に変更
        tick_dates = []
        tick_labels = []
        
        # 最初の日を追加
        tick_dates.append(date_range[0].toordinal())
        tick_labels.append(date_range[0].strftime('%m-%d'))
        
        # 5日ごとの目盛りを追加
        for i in range(len(date_range)):
            if i % 5 == 0:  # 5日ごと
                tick_dates.append(date_range[i].toordinal())
                tick_labels.append(date_range[i].strftime('%m-%d'))
        
        # 最後の日を追加（まだ追加されていない場合）
        if date_range[-1].toordinal() not in tick_dates:
            tick_dates.append(date_range[-1].toordinal())
            tick_labels.append(date_range[-1].strftime('%m-%d'))

        # x軸の設定を適用
        ax.set_xticks(tick_dates)
        ax.set_xticklabels(tick_labels, rotation=0, fontproperties=jp_font)

        # tight_layoutを削除
        # plt.tight_layout() の代わりに以下を使用
        plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
        
        return fig

    except Exception as e:
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
