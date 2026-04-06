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
        
        # 列構成: 1:en, 2:ja, 3:correct_count, 4:no, 5:total_shown, 6:is_done(1=完了, 0=未完)
        if en in cells:
            row_idx = cells.index(en) + 1
            row_data = sheet.row_values(row_idx)
            
            # 1. 出題回数更新 (5列目)
            shown_val = row_data[4] if len(row_data) >= 5 else 0
            new_shown = int(float(shown_val)) + 1 if str(shown_val).replace('.','').isdigit() else 1
            sheet.update_cell(row_idx, 5, new_shown)

            # 2. 正解/不正解の処理
            if res_type == 'ok':
                val = row_data[2] if len(row_data) >= 3 else 0
                curr = int(float(val)) if str(val).replace('.','').isdigit() else 0
                new_count = curr + 1
                
                if new_count >= 5:
                    sheet.update_cell(row_idx, 3, 5)
                    sheet.update_cell(row_idx, 6, 1) # 「完了」フラグを立てる
                else:
                    sheet.update_cell(row_idx, 3, new_count)
            else:
                # 間違えたら「未完了」に戻して正解数リセット
                sheet.update_cell(row_idx, 3, 0)
                sheet.update_cell(row_idx, 6, 0)
        else:
            # 新規登録（まだシートにない単語）
            try: word_no = int(float(word_dict.get('no', 0)))
            except: word_no = 0
            
            if res_type == 'ok':
                # 初回で正解した場合は「完了」として登録（復習リストには出さない）
                sheet.append_row([en, word_dict['ja'], 5, word_no, 1, 1])
            else:
                # 間違えた場合は「未完了」として登録
                sheet.append_row([en, word_dict['ja'], 0, word_no, 1, 0])
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
# 「完了(is_done=1)」ではないものだけを復習リストとする
pending_words = [d for d in gs_rows if str(d.get('is_done', 0)) != '1']
gs_dict = {str(d.get('en')): d for d in gs_rows if d.get('en')}

# --- 5. サイドバー ---
st.sidebar.title("🎓 学習メニュー")
mode = st.sidebar.selectbox("モード", ["英→日クイズ", "日→英クイズ", "単語帳"])

st.sidebar.divider()
st.sidebar.metric("現在の復習が必要な単語数", f"{len(pending_words)} 語")

if mode != "単語帳":
    nos = [int(w['no']) for w in st.session_state.all_words] or [0]
    s_no = st.sidebar.number_input("開始No.", min(nos), max(nos), min(nos))
    e_no = st.sidebar.number_input("終了No.", min(nos), max(nos), max(nos))
    quiz_target = st.sidebar.radio("出題対象", ["全問", "復習のみ"], horizontal=True)
    
    if quiz_target == "復習のみ":
        active_list = pending_words
    else:
        active_list = [w for w in st.session_state.all_words if s_no <= w['no'] <= e_no]

# --- 6. メインコンテンツ ---
if mode == "単語帳":
    st.title("📖 単語帳")
    st.dataframe(pd.DataFrame(st.session_state.all_words)[['no', 'en', 'ja']], hide_index=True, use_container_width=True)

else:
    if 'q' not in st.session_state or st.session_state.get('reset_q'):
        if not active_list:
            st.warning("対象となる単語がありません。")
            st.stop()
        
        weights = []
        for w in active_list:
            shown_count = gs_dict.get(str(w['en']), {}).get('total_shown', 0)
            weights.append(1.0 / (float(shown_count) + 1.0) if str(shown_count).replace('.','').isdigit() else 1.0)
        
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
    status_display = ""
    
    if matching_gs:
        # 正解数と完了状態の表示
        is_done = str(matching_gs.get('is_done', 0)) == '1'
        if is_done:
            status_display = " | ✅ 完了済み"
        else:
            raw_ok = matching_gs.get('count', 0)
            curr_ok = int(float(raw_ok)) if str(raw_ok).replace('.','').isdigit() else 0
            status_display = f" | 🔥 あと {max(0, 5 - curr_ok)} 回"
        
        total_s = matching_gs.get('total_shown', 0)
        status_display += f" | 📊 学習: {total_s}回目"
    else:
        status_display = " | 📊 学習: 初回"

    st.write(f"No.{display_no}{status_display}")
    
    # ... (以下、クイズ表示とボタン処理は前回のコードと同じ) ...
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