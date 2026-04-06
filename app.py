import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- 1. ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- 2. スタイル設定 (判定色ボタン) ---
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
    except:
        return None

@st.cache_data(ttl=300)
def load_gs_data():
    sheet = get_sheet()
    if sheet:
        try:
            return sheet.get_all_records()
        except: return []
    return []

def sync_result(word_dict, res_type):
    sheet = get_sheet()
    if not sheet: return
    try:
        en = word_dict['en']
        if res_type == 'ok':
            cell = sheet.find(en)
            if cell:
                curr = int(sheet.cell(cell.row, 3).value or 0)
                if curr + 1 >= 5: sheet.delete_rows(cell.row)
                else: sheet.update_cell(cell.row, 3, curr + 1)
        else:
            cells = sheet.col_values(1)
            if en not in cells:
                sheet.append_row([en, word_dict['ja'], 0, int(float(word_dict.get('no', 0)))])
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

wrong_data = load_gs_data()
st.session_state.wrong_words = [d for d in wrong_data if d.get('en')]

# --- 5. サイドバー (設定・情報表示) ---
st.sidebar.title("🎓 学習メニュー")
mode = st.sidebar.selectbox("モード選択", ["英→日クイズ", "日→英クイズ", "単語帳"])

# 復習問題数の表示
st.sidebar.divider()
st.sidebar.metric("現在の復習問題数", f"{len(st.session_state.wrong_words)} 語")

if mode != "単語帳":
    st.sidebar.markdown("---")
    nos = [int(w['no']) for w in st.session_state.all_words] or [0]
    s_no = st.sidebar.number_input("開始No.", min(nos), max(nos), min(nos))
    e_no = st.sidebar.number_input("終了No.", min(nos), max(nos), max(nos))
    quiz_target = st.sidebar.radio("出題対象", ["全問", "復習"], horizontal=True)
    active_list = st.session_state.wrong_words if quiz_target == "復習" else [w for w in st.session_state.all_words if s_no <= w['no'] <= e_no]
else:
    active_list = st.session_state.all_words

# --- 6. メインコンテンツ ---

# --- 単語帳モード ---
if mode == "単語帳":
    st.title("📖 単語帳")
    st.write("CSVの全単語を一覧表示します。")
    df_display = pd.DataFrame(st.session_state.all_words)
    st.dataframe(df_display[['no', 'en', 'ja']], hide_index=True, use_container_width=True)

# --- クイズモード (英→日 / 日→英) ---
else:
    if 'q' not in st.session_state or st.session_state.get('reset_q'):
        if not active_list:
            st.warning("対象となる単語がありません。設定を確認してください。")
            st.stop()
        target = random.choice(active_list)
        pool = st.session_state.all_words
        others = random.sample([w for w in pool if w['en'] != target['en']], 3)
        choices = others + [target]
        random.shuffle(choices)
        st.session_state.q = {"t": target, "c": choices, "ans": False}
        st.session_state.reset_q = False

    q = st.session_state.q
    st.write(f"No.{int(float(q['t']['no']))}")
    
    # モードによって問題の表示を切り替え
    question_text = q['t']['en'] if mode == "英→日クイズ" else q['t']['ja']
    st.markdown(f"# {question_text}")

    if not q["ans"]:
        cols = st.columns(2)
        for i, c in enumerate(q["c"]):
            # モードによって選択肢の表示を切り替え
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
        # 回答後の表示
        correct_answer = f"{q['t']['en']} : {q['t']['ja']}"
        if st.session_state.res_type == "ok":
            set_button_color("#28a745")
            st.success(f"🎯 正解！\n\n{correct_answer}")
        else:
            set_button_color("#dc3545")
            if st.session_state.res_type == "unknown":
                st.warning(f"💡 答え\n\n{correct_answer}")
            else:
                st.error(f"❌ 残念...\n\n正解は: {correct_answer}")
        
        if st.button("次の問題へ ➡️", use_container_width=True):
            st.session_state.reset_q = True
            st.rerun()

        st.divider()
        for c in q["c"]:
            mark = "✅" if c['en'] == q['t']['en'] else "・"
            st.write(f"{mark} **{c['en']}**: {c['ja']}")