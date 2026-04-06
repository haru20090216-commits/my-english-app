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
    except Exception as e:
        st.sidebar.error(f"GS連携エラー: {e}")
        return None

def add_wrong_word_to_gs(word_dict):
    sheet = get_spreadsheet()
    if sheet:
        try:
            existing = sheet.col_values(1)
            if word_dict['en'] not in existing:
                no_val = word_dict.get('no', 0)
                sheet.append_row([word_dict['en'], word_dict['ja'], 0, int(no_val)])
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
            # get_all_recordsでエラーが出る場合（空の場合など）の対策
            data = sheet.get_all_records()
            return data if data else []
        except: return []
    return []

# --- データの初期読み込み ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_base_data()
# 復習単語は常に最新を読み込むか、セッション開始時にリセット
if 'wrong_words' not in st.session_state:
    st.session_state.wrong_words = load_wrong_words()

# --- サイドバー設定 ---
st.sidebar.title("🔍 メニュー")
main_mode = st.sidebar.radio("モード切替:", ["クイズ", "単語帳"], horizontal=True)

st.sidebar.markdown("---")
st.sidebar.title("🛠 設定")

if st.session_state.all_words:
    all_nos = [int(w['no']) for w in st.session_state.all_words]
    start_no = st.sidebar.number_input("開始番号", min(all_nos), max(all_nos), min(all_nos))
    end_no = st.sidebar.number_input("終了番号", min(all_nos), max(all_nos), max(all_nos))
    filtered_words = [w for w in st.session_state.all_words if start_no <= int(w['no']) <= end_no]
    
    # 範囲変更検知
    if 'last_range' not in st.session_state or st.session_state.last_range != (start_no, end_no):
        st.session_state.last_range = (start_no, end_no)
        if 'current_question' in st.session_state: del st.session_state.current_question
else:
    filtered_words = []

if main_mode == "クイズ":
    direction = st.sidebar.radio("出題形式:", ["英 → 日", "日 → 英"], horizontal=True)
    if 'last_dir' not in st.session_state or st.session_state.last_dir != direction:
        st.session_state.last_dir = direction
        if 'current_question' in st.session_state: del st.session_state.current_question

    # 【重要】復習単語数の表示
    wrong_list = st.session_state.wrong_words
    st.sidebar.metric("現在の復習単語数", f"{len(wrong_list)} 語")
    
    quiz_sub_mode = st.sidebar.radio("対象:", ["全問", "復習"], horizontal=True)
    if 'last_q_mode' not in st.session_state or st.session_state.last_q_mode != quiz_sub_mode:
        st.session_state.last_q_mode = quiz_sub_mode
        if 'current_question' in st.session_state: del st.session_state.current_question

# --- メインコンテンツ ---
if main_mode == "単語帳":
    st.title("📑 単語帳一覧")
    if not filtered_words:
        st.warning("表示する単語がありません。")
    else:
        for w in filtered_words:
            col1, col2, col3 = st.columns([1, 4, 4])
            col1.write(f"{int(w['no'])}")
            col2.write(f"**{w['en']}**")
            col3.write(f"{w['ja']}")
            st.divider()

elif main_mode == "クイズ":
    # 出題リストの決定
    active_list = st.session_state.wrong_words if (quiz_sub_mode == "復習" and st.session_state.wrong_words) else filtered_words

    if 'current_question' not in st.session_state:
        if not active_list:
            st.session_state.current_question = None
        else:
            target = random.choice(active_list)
            # 他の選択肢（choices）を全単語から作成
            others = [w for w in st.session_state.all_words if w['en'] != target['en']]
            # 選択肢が足りない場合の対策
            sample_size = min(len(others), 3)
            choices = random.sample(others, sample_size) + [target]
            random.shuffle(choices)
            st.session_state.current_question = {"target": target, "choices": choices, "answered": False}

    if st.session_state.current_question is None:
        st.warning("出題できる単語がありません。範囲設定を広げるか、全問モードに切り替えてください。")
    else:
        q = st.session_state.current_question
        t_data = q['target']
        
        # 安全な表示処理
        q_no = t_data.get('no', '?')
        q_count = t_data.get('count', 0)
        try: d_count = int(q_count)
        except: d_count = 0
        
        c_info = f" (あと {5 - d_count} 回)" if quiz_sub_mode == "復習" else ""
        st.markdown(f"### No.{q_no}{c_info}")
        
        q_text = t_data['en'] if direction == "英 → 日" else t_data['ja']
        st.markdown(f"# **{q_text}**")

        if not q["answered"]:
            cols = st.columns(2)
            for i, choice in enumerate(q["choices"]):
                label = choice['ja'] if direction == "英 → 日" else choice['en']
                with cols[i % 2]:
                    if st.button(label, key=f"btn_{i}", use_container_width=True):
                        q["answered"] = True
                        if choice['en'] == t_data['en']:
                            st.session_state.res_type = "ok"
                            update_correct_count_in_gs(t_data['en'])
                        else:
                            st.session_state.res_type = "ng"
                            add_wrong_word_to_gs(t_data)
                        st.session_state.wrong_words = load_wrong_words()
                        st.rerun()
            
            if st.button("❓ わからない", key="dont_know", use_container_width=True):
                q["answered"] = True
                st.session_state.res_type = "unknown"
                add_wrong_word_to_gs(t_data)
                st.session_state.wrong_words = load_wrong_words()
                st.rerun()
        else:
            if st.session_state.res_type == "ok":
                st.success(f"🎯 正解！: {t_data['en']} = {t_data['ja']}")
            else:
                st.error(f"❌ 正解は: {t_data['en']} = {t_data['ja']}")
            
            if st.button("次の問題へ ➡️", use_container_width=True):
                del st.session_state.current_question
                st.rerun()