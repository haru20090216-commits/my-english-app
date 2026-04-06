import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- Googleスプレッドシート連携 ---
@st.cache_resource
def get_spreadsheet():
    try:
        raw_key = st.secrets["json_key"].strip().lstrip('.')
        info = json.loads(raw_key)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except:
        return None

def add_wrong_word_to_gs(word_dict):
    sheet = get_spreadsheet()
    if sheet:
        try:
            existing = sheet.col_values(1)
            if word_dict['en'] not in existing:
                no_val = word_dict.get('no', 0)
                sheet.append_row([word_dict['en'], word_dict['ja'], 0, no_val])
        except: pass

def update_correct_count_in_gs(en_word):
    sheet = get_spreadsheet()
    if not sheet: return False
    try:
        cell = sheet.find(en_word)
        if cell:
            val = sheet.cell(cell.row, 3).value
            current_count = int(val) if val and str(val).isdigit() else 0
            new_count = current_count + 1
            if new_count >= 5:
                sheet.delete_rows(cell.row)
                return True
            else:
                sheet.update_cell(cell.row, 3, new_count)
                return False
    except: pass
    return False

@st.cache_data
def load_base_data():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            if 'no' in df.columns:
                df['no'] = pd.to_numeric(df['no'], errors='coerce')
            return df.dropna(subset=['en', 'ja', 'no']).to_dict('records')
        except: continue
    return []

def load_wrong_words():
    sheet = get_spreadsheet()
    if sheet:
        try:
            return sheet.get_all_records()
        except: return []
    return []

if 'all_words' not in st.session_state:
    st.session_state.all_words = load_base_data()
if 'wrong_words' not in st.session_state:
    st.session_state.wrong_words = load_wrong_words()

# --- サイドバー設定 ---
st.sidebar.title("🔍 メニュー")
main_mode = st.sidebar.radio("モード切替:", ["クイズ", "単語帳"], horizontal=True)

st.sidebar.markdown("---")
st.sidebar.title("🛠 出題・表示設定")

if st.session_state.all_words:
    nos = [int(w['no']) for w in st.session_state.all_words]
    start_no = st.sidebar.number_input("開始番号", min(nos), max(nos), min(nos))
    end_no = st.sidebar.number_input("終了番号", min(nos), max(nos), max(nos))
    filtered_words = [w for w in st.session_state.all_words if start_no <= int(w['no']) <= end_no]
    
    # 範囲変更検知
    c_range = (start_no, end_no)
    if 'last_range' not in st.session_state or st.session_state.last_range != c_range:
        st.session_state.last_range = c_range
        if 'current_question' in st.session_state: del st.session_state.current_question
else:
    filtered_words = []

if main_mode == "クイズ":
    direction = st.sidebar.radio("出題形式:", ["英 → 日", "日 → 英"], horizontal=True)
    if 'last_dir' not in st.session_state: st.session_state.last_dir = direction
    if st.session_state.last_dir != direction:
        st.session_state.last_dir = direction
        if 'current_question' in st.session_state: del st.session_state.current_question

    wrong_count = len(st.session_state.wrong_words)
    st.sidebar.metric("現在の復習単語数", f"{wrong_count} 語")
    quiz_sub_mode = st.sidebar.radio("対象:", ["全問", "復習"], horizontal=True)
    if 'last_q_mode' not in st.session_state: st.session_state.last_q_mode = quiz_sub_mode
    if st.session_state.last_q_mode != quiz_sub_mode:
        st.session_state.last_q_mode = quiz_sub_mode
        if 'current_question' in st.session_state: del st.session_state.current_question

# --- メインコンテンツ ---

# 1. 単語帳モード
if main_mode == "単語帳":
    st.title("📑 単語帳一覧")
    st.write(f"No.{start_no} から No.{end_no} までの単語を表示中")
    st.markdown("---")
    
    # ヘッダー
    h_col1, h_col2, h_col3 = st.columns([1, 4, 4])
    with h_col1: st.markdown("**No.**")
    with h_col2: st.markdown("**英語**")
    with h_col3: st.markdown("**日本語**")
    st.markdown("---")

    for w in filtered_words:
        col1, col2, col3 = st.columns([1, 4, 4])
        with col1: st.write(f"{int(w['no'])}")
        with col2: st.write(f"**{w['en']}**")
        with col3: st.write(f"{w['ja']}")
        st.divider()

# 2. クイズモード
elif main_mode == "クイズ":
    active_list = st.session_state.wrong_words if (quiz_sub_mode == "復習" and st.session_state.wrong_words) else filtered_words

    if 'current_question' not in st.session_state:
        if not active_list:
            st.session_state.current_question = None
        else:
            target = random.choice(active_list)
            others = [w for w in st.session_state.all_words if w['en'] != target['en']]
            choices = random.sample(others, min(len(others), 3)) + [target]
            random.shuffle(choices)
            st.session_state.current_question = {"target": target, "choices": choices, "answered": False}

    if st.session_state.current_question is None:
        st.warning("表示できる単語がありません。範囲設定を確認してください。")
    else:
        q = st.session_state.current_question
        target_data = q['target']
        
        q_no = target_data.get('no', '?')
        q_count = target_data.get('count', 0)
        try: display_count = int(q_count)
        except: display_count = 0
        
        c_info = f" (あと {5 - display_count} 回)" if quiz_sub_mode == "復習" else ""
        st.markdown(f"### No.{q_no}{c_info}")
        
        question_text = target_data['en'] if direction == "英 → 日" else target_data['ja']
        st.markdown(f"# **{question_text}**")

        if not q["answered"]:
            cols = st.columns(2)
            for i, choice in enumerate(q["choices"]):
                btn_label = choice['ja'] if direction == "英 → 日" else choice['en']
                with cols[i % 2]:
                    if st.button(btn_label, key=f"btn_{i}", use_container_width=True):
                        q["answered"] = True
                        if choice['en'] == target_data['en']:
                            st.session_state.res_type = "ok"
                            update_correct_count_in_gs(target_data['en'])
                        else:
                            st.session_state.res_type = "ng"
                            add_wrong_word_to_gs(target_data)
                        st.session_state.wrong_words = load_wrong_words()
                        st.rerun()
            
            if st.button("❓ わからない", key="dont_know", use_container_width=True):
                q["answered"] = True
                st.session_state.res_type = "unknown"
                add_wrong_word_to_gs(target_data)
                st.session_state.wrong_words = load_wrong_words()
                st.rerun()
        else:
            if st.session_state.res_type == "ok":
                st.success(f"🎯 正解！: {target_data['en']} = {target_data['ja']}")
            else:
                st.error(f"❌ 正解は: {target_data['en']} = {target_data['ja']}")
            
            st.write("---")
            if st.button("次の問題へ ➡️", use_container_width=True):
                del st.session_state.current_question
                st.rerun()