import streamlit as st
import random
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

@st.cache_data(ttl=30)
def load_gs_data():
    sheet = get_sheet()
    if not sheet: return []
    try:
        return sheet.get_all_records()
    except: return []

def sync_result(word_dict, res_type):
    sheet = get_sheet()
    if not sheet: return
    try:
        en = word_dict['en']
        cells = sheet.col_values(1)
        
        if en in cells:
            row_idx = cells.index(en) + 1
            # 出題回数の更新 (5列目)
            try:
                row_data = sheet.row_values(row_idx)
                shown_val = row_data[4] if len(row_data) >= 5 else 0
                new_shown = int(float(shown_val)) + 1 if str(shown_val).replace('.','').isdigit() else 1
                sheet.update_cell(row_idx, 5, new_shown)
            except: pass

            if res_type == 'ok':
                val = sheet.cell(row_idx, 3).value
                curr = int(float(val)) if val and str(val).replace('.','').isdigit() else 0
                if curr + 1 >= 5:
                    sheet.delete_rows(row_idx) # 5回達成で卒業
                else:
                    sheet.update_cell(row_idx, 3, curr + 1)
            else:
                sheet.update_cell(row_idx, 3, 0) # 不正解でリセット
        else:
            # スプレッドシートにない単語が「全問モード」等で出た場合
            try: word_no = int(float(word_dict.get('no', 0)))
            except: word_no = 0
            # 初回登録: [en, ja, 正解数, no, 出題回数]
            # 正解した場合は正解数1、それ以外は0で登録
            init_ok = 1 if res_type == 'ok' else 0
            sheet.append_row([en, word_dict['ja'], init_ok, word_no, 1])
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
            df['no'] = pd.to_numeric(df.get('no', 0), errors='coerce').fillna(0)
            return df.dropna(subset=['en', 'ja']).to_dict('records')
        except: continue
    return []

# --- 4. データ準備 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_csv()

gs_rows = load_gs_data()
gs_dict = {str(d.get('en')): d for d in gs_rows if d.get('en')}

# --- 5. サイドバー ---
st.sidebar.title("🎓 学習メニュー")
mode = st.sidebar.selectbox("モード", ["英→日クイズ", "日→英クイズ", "単語帳"])

st.sidebar.divider()
st.sidebar.metric("現在の復習が必要な単語数", f"{len(gs_rows)} 語")

if mode != "単語帳":
    nos = [int(w['no']) for w in st.session_state.all_words] or [0]
    s_no = st.sidebar.number_input("開始No.", min(nos), max(nos), min(nos))
    e_no = st.sidebar.number_input("終了No.", min(nos), max(nos), max(nos))
    quiz_target = st.sidebar.radio("出題対象", ["全問", "復習のみ"], horizontal=True)
    
    if quiz_target == "復習のみ":
        active_list = [d for d in gs_rows if d.get('en')]
    else:
        active_list = [w for w in st.session_state.all_words if s_no <= w['no'] <= e_no]

# 出題順序リセットボタン (復習データは維持)
st.sidebar.markdown("---")
if st.sidebar.button("🔄 出題頻度のみリセット", use_container_width=True):
    sheet = get_sheet()
    if sheet:
        rows = len(sheet.get_all_values())
        if rows > 1:
            cell_list = sheet.range(2, 5, rows, 5)
            for cell in cell_list: cell.value = 0
            sheet.update_cells(cell_list)
        st.cache_data.clear()
        st.success("出題頻度をリセットしました！")
        st.rerun()

# --- 6. メインコンテンツ ---
if mode == "単語帳":
    st.title("📖 単語帳")
    st.dataframe(pd.DataFrame(st.session_state.all_words)[['no', 'en', 'ja']], hide_index=True, use_container_width=True)

else:
    if 'q' not in st.session_state or st.session_state.get('reset_q'):
        if not active_list:
            st.warning("対象となる単語がありません。")
            st.stop()
        
        # 重み付け選択: 出題回数が少ないほど選ばれやすく
        weights = []
        for w in active_list:
            shown_count = gs_dict.get(str(w['en']), {}).get('total_shown', 0)
            try: s_num = float(shown_count)
            except: s_num = 0.0
            weights.append(1.0 / (s_num + 1.0))
        
        target = random.choices(active_list, weights=weights, k=1)[0]
        others = random.sample([w for w in st.session_state.all_words if w['en'] != target['en']], min(len(st.session_state.all_words)-1, 3))
        choices = others + [target]
        random.shuffle(choices)
        st.session_state.q = {"t": target, "c": choices, "ans": False}
        st.session_state.reset_q = False

    q = st.session_state.q
    try: display_no = int(float(q['t'].get('no', 0)))
    except: display_no = 0
        
    matching_gs = gs_dict.get(str(q['t']['en']), {})
    count_display = ""
    shown_display = ""
    
    # スプレッドシートにある場合のみ詳細を表示
    if matching_gs:
        raw_ok = matching_gs.get('count', matching_gs.get('正解数', 0))
        try: curr_ok = int(float(raw_ok)) if str(raw_ok).replace('.','').isdigit() else 0
        except: curr_ok = 0
        count_display = f" | 🔥 あと {max(0, 5 - curr_ok)} 回"
        
        raw_shown = matching_gs.get('total_shown', 0)
        try: total_s = int(float(raw_shown)) if str(raw_shown).replace('.','').isdigit() else 0
        except: total_s = 0
        shown_display = f" | 📊 学習: {total_s}回目"
    else:
        # 初見の単語（スプレッドシート未登録）の場合
        shown_display = " | 📊 学習: 初回"

    st.write(f"No.{display_no}{count_display}{shown_display}")
    
    question_text = q['t']['en'] if mode == "英→日クイズ" else q['t']['ja']
    st.markdown(f"# {question_text}")

    if not q["ans"]:
        cols = st.columns(2)
        for i, c in enumerate(q["c"]):
            choice_text = c['ja'] if mode == "英→日クイズ" else c['en']
            with cols[i % 2]:
                if st.button(choice_text, key=f"b{i}", use_container_width=True):
                    q["ans"] = True
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
        ans_text = f"{q['t']['en']} : {q['t']['ja']}"
        if st.session_state.res_type == "ok":
            set_button_color("#28a745")
            st.success(f"🎯 正解！\n\n{ans_text}")
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