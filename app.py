import streamlit as st
import random
import time
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- 1. ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- 2. スタイル設定 ---
def set_button_color(color_code):
    st.markdown(f"""
        <style>
        div.stButton > button:first-child {{
            background-color: {color_code} !important;
            color: white !important;
            border: None !important;
        }}
        </style>
    """, unsafe_allow_html=True)

# --- 3. Googleスプレッドシート連携 ---
@st.cache_resource
def get_sheet():
    try:
        raw_key = st.secrets["json_key"].strip().lstrip('.')
        info = json.loads(raw_key)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except: return None

@st.cache_data(ttl=60) # 復習状況を反映するためキャッシュは1分に短縮
def load_gs_data():
    sheet = get_sheet()
    if not sheet: return []
    # [英, 日, 正解数, No] の形式を想定
    return sheet.get_all_records()

def sync_result(word_dict, res_type):
    sheet = get_sheet()
    if not sheet: return
    try:
        en = word_dict['en']
        # スプレッドシートから該当単語を探す
        cells = sheet.col_values(1)
        
        if res_type == 'ok':
            if en in cells:
                row_idx = cells.index(en) + 1
                # 現在の正解数を取得
                val = sheet.cell(row_idx, 3).value
                curr = int(val) if val and str(val).isdigit() else 0
                new_count = curr + 1
                
                if new_count >= 5:
                    sheet.delete_rows(row_idx) # 5回達成で削除
                else:
                    sheet.update_cell(row_idx, 3, new_count) # カウントアップ
        else:
            # 不正解または「わからない」または「時間切れ」
            if en not in cells:
                # リストになければ新規追加（正解数0からスタート）
                sheet.append_row([en, word_dict['ja'], 0, int(float(word_dict.get('no', 0)))])
            else:
                # すでにリストにある場合は、正解数を「0」にリセット（厳しいルールにする場合）
                # リセットしたくない場合はこの行をコメントアウトしてください
                row_idx = cells.index(en) + 1
                sheet.update_cell(row_idx, 3, 0)
                
    except: pass
    st.cache_data.clear()

@st.cache_data
def load_csv():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            df['no'] = pd.to_numeric(df.get('no', range(1, len(df)+1)), errors='coerce').fillna(0)
            return df.dropna(subset=['en', 'ja']).to_dict('records')
        except: continue
    return []

# --- 4. データ準備 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_csv()

# スプレッドシートから復習データを取得
gs_rows = load_gs_data()
# 正解数を保持した状態でセッションに格納
st.session_state.wrong_words = [d for d in gs_rows if d.get('en')]

# --- 5. サイドバー ---
st.sidebar.title("🎓 学習メニュー")
mode = st.sidebar.selectbox("モード", ["英→日クイズ", "日→英クイズ", "単語帳"])
limit_sec = st.sidebar.slider("制限時間 (秒)", 3, 20, 10)

st.sidebar.divider()
st.sidebar.metric("現在の復習が必要な単語数", f"{len(st.session_state.wrong_words)} 語")

if mode != "単語帳":
    nos = [int(w['no']) for w in st.session_state.all_words] or [0]
    s_no = st.sidebar.number_input("開始No.", min(nos), max(nos), min(nos))
    e_no = st.sidebar.number_input("終了No.", min(nos), max(nos), max(nos))
    quiz_target = st.sidebar.radio("出題対象", ["全問", "復習"], horizontal=True)
    active_list = st.session_state.wrong_words if quiz_target == "復習" else [w for w in st.session_state.all_words if s_no <= w['no'] <= e_no]

# --- 6. メインコンテンツ ---
if mode == "単語帳":
    st.title("📖 単語帳")
    st.dataframe(pd.DataFrame(st.session_state.all_words)[['no', 'en', 'ja']], hide_index=True, use_container_width=True)

else:
    if 'q' not in st.session_state or st.session_state.get('reset_q'):
        if not active_list:
            st.warning("対象となる単語がありません。")
            st.stop()
        target = random.choice(active_list)
        pool = st.session_state.all_words
        others = random.sample([w for w in pool if w['en'] != target['en']], 3)
        choices = others + [target]
        random.shuffle(choices)
        st.session_state.q = {"t": target, "c": choices, "ans": False, "start_time": time.time()}
        st.session_state.reset_q = False

    q = st.session_state.q
    
    # --- 残り回数の表示ロジック ---
    # スプレッドシートにある単語なら残り回数を計算
    matching_wrong = next((w for w in st.session_state.wrong_words if w['en'] == q['t']['en']), None)
    count_display = ""
    if matching_wrong:
        # 'count' またはスプレッドシートの3列目の項目名に合わせて取得
        current_ok = matching_wrong.get('count', matching_wrong.get('正解数', 0))
        try:
            left = 5 - int(current_ok)
            count_display = f" 🔥 あと {max(0, left)} 回正解でクリア！"
        except: pass

    st.write(f"No.{int(float(q['t']['no']))}{count_display}")
    
    question_text = q['t']['en'] if mode == "英→日クイズ" else q['t']['ja']
    st.markdown(f"# {question_text}")

    if not q["ans"]:
        cols = st.columns(2)
        for i, c in enumerate(q["c"]):
            choice_text = c['ja'] if mode == "英→日クイズ" else c['en']
            with cols[i % 2]:
                if st.button(choice_text, key=f"b{i}", use_container_width=True):
                    elapsed = time.time() - q["start_time"]
                    q["ans"] = True
                    if elapsed > limit_sec:
                        st.session_state.res_type = "timeout"
                        sync_result(q['t'], "ng")
                    else:
                        is_correct = (c['en'] == q['t']['en'])
                        st.session_state.res_type = "ok" if is_correct else "ng"
                        sync_result(q['t'], st.session_state.res_type)
                    st.rerun()
        
        if st.button("❓ わからない", use_container_width=True):
            q["ans"] = True
            st.session_state.res_type = "unknown"
            sync_result(q['t'], "unknown")
            st.rerun()
    else:
        # 回答後の表示
        ans_text = f"{q['t']['en']} : {q['t']['ja']}"
        if st.session_state.res_type == "ok":
            set_button_color("#28a745")
            st.success(f"🎯 正解！\n\n{ans_text}")
        elif st.session_state.res_type == "timeout":
            set_button_color("#ffc107")
            st.warning(f"⏰ 時間切れ！ ({limit_sec}秒以内)\n\n正解は: {ans_text}")
        else:
            set_button_color("#dc3545")
            msg = "💡 答え" if st.session_state.res_type == "unknown" else "❌ 残念..."
            st.error(f"{msg}\n\n正解は: {ans_text}")
        
        if st.button("次の問題へ ➡️", use_container_width=True):
            st.session_state.reset_q = True
            st.rerun()

        st.divider()
        for c in q["c"]:
            mark = "✅" if c['en'] == q['t']['en'] else "・"
            st.write(f"{mark} **{c['en']}**: {c['ja']}")