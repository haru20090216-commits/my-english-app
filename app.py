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
        /* 問題文を中央寄せで巨大化 */
        .question-text {{
            text-align: center;
            font-size: 3.5rem !important;
            font-weight: 800;
            padding: 20px 0;
            line-height: 1.2;
        }}
        /* ステータス情報の表示スタイル */
        .status-text {{
            font-size: 1.0rem;
            color: #555;
            text-align: center;
            margin-bottom: 5px;
            font-weight: 500;
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

@st.cache_data(ttl=5)
def load_gs_data():
    sheet = get_sheet()
    if not sheet: return []
    try:
        data = sheet.get_all_values()
        if len(data) < 2: return []
        rows = []
        for r in data[1:]:
            rows.append({
                'en': r[0] if len(r) > 0 else "",
                'ja': r[1] if len(r) > 1 else "",
                'count': r[2] if len(r) > 2 else 0,
                'no': r[3] if len(r) > 3 else 0,
                'total_shown': r[4] if len(r) > 4 else 0,
                'is_done': r[5] if len(r) > 5 else 0
            })
        return rows
    except: return []

def sync_result(word_dict, res_type):
    sheet = get_sheet()
    if not sheet: return
    try:
        en_target = str(word_dict['en']).strip()
        all_col1 = [str(x).strip() for x in sheet.col_values(1)]
        
        if en_target in all_col1:
            row_idx = all_col1.index(en_target) + 1
            row_data = sheet.row_values(row_idx)
            # 学習回数を更新
            try:
                raw_shown = row_data[4] if len(row_data) >= 5 else 0
                old_shown = int(float(str(raw_shown).strip())) if str(raw_shown).strip() else 0
            except: old_shown = 0
            sheet.update_cell(row_idx, 5, old_shown + 1)

            # 正解数を更新
            if res_type == 'ok':
                try:
                    raw_count = row_data[2] if len(row_data) >= 3 else 0
                    old_count = int(float(str(raw_count).strip())) if str(raw_count).strip() else 0
                except: old_count = 0
                new_count = old_count + 1
                if new_count >= 5:
                    sheet.update_cell(row_idx, 3, 5); sheet.update_cell(row_idx, 6, 1)
                else:
                    sheet.update_cell(row_idx, 3, new_count)
            else:
                sheet.update_cell(row_idx, 3, 0); sheet.update_cell(row_idx, 6, 0)
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
set_button_color("#31333F") # デフォルトカラー

if 'all_words' not in st.session_state:
    st.session_state.all_words = load_csv()

gs_rows = load_gs_data()
pending_words = [d for d in gs_rows if d.get('en') and str(d.get('is_done', 0)) != '1']
gs_dict = {str(d.get('en')).strip(): d for d in gs_rows if d.get('en')}

# --- 5. サイドバー ---
st.sidebar.title("🎓 学習メニュー")
mode = st.sidebar.selectbox("モード", ["英→日クイズ", "日→英クイズ", "単語帳"])
st.sidebar.divider()
st.sidebar.metric("復習が必要な単語数", f"{len(pending_words)} 語")

if mode != "単語帳":
    nos = [int(w['no']) for w in st.session_state.all_words] or [0]
    col1, col2 = st.sidebar.columns(2)
    with col1: s_no = st.number_input("開始No.", min(nos), max(nos), min(nos))
    with col2: e_no = st.number_input("終了No.", min(nos), max(nos), max(nos))
    quiz_target = st.sidebar.radio("出題対象", ["全問", "復習のみ"], horizontal=True)

    # 設定変更時のリセットロジック
    current_settings = f"{s_no}-{e_no}-{quiz_target}-{mode}"
    if 'last_settings' in st.session_state and st.session_state.last_settings != current_settings:
        st.session_state.reset_q = True
    st.session_state.last_settings = current_settings

    active_list = pending_words if quiz_target == "復習のみ" else [w for w in st.session_state.all_words if s_no <= w['no'] <= e_no]

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
            st.session_state.reset_q = True
            st.success("頻度データをリセットしました")
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
        
        # 学習回数に基づく重み付け
        weights = []
        for w in active_list:
            match = gs_dict.get(str(w['en']).strip(), {})
            try: s_num = float(str(match.get('total_shown', 0)).strip())
            except: s_num = 0.0
            weights.append(1.0 / (s_num + 1.0))
        
        target = random.choices(active_list, weights=weights, k=1)[0]
        others = random.sample([w for w in st.session_state.all_words if str(w['en']).strip() != str(target['en']).strip()], min(len(st.session_state.all_words)-1, 3))
        choices = others + [target]
        random.shuffle(choices)
        st.session_state.q = {"t": target, "c": choices, "ans": False}
        st.session_state.reset_q = False

    q = st.session_state.q
    matching_gs = gs_dict.get(str(q['t']['en']).strip(), {})
    
    # ステータス表示の組み立て
    display_no = int(float(q['t'].get('no', 0)))
    try: total_s = int(float(str(matching_gs.get('total_shown', 0)).strip())) if matching_gs else 0
    except: total_s = 0
    try: curr_ok = int(float(str(matching_gs.get('count', 0)).strip())) if matching_gs else 0
    except: curr_ok = 0
    
    # メイン画面上部のステータス（復習語数はサイドバーにあるため表示しない）
    st.markdown(f"""
        <p class="status-text">
            No.{display_no} | 📊 学習: {total_s}回目 | 🔥 あと {max(0, 5 - curr_ok)} 回で完了
        </p>
    """, unsafe_allow_html=True)
    
    # 問題文の巨大表示
    question_text = q['t']['en'] if mode == "英→日クイズ" else q['t']['ja']
    st.markdown(f'<div class="question-text">{question_text}</div>', unsafe_allow_html=True)

    if not q["ans"]:
        cols = st.columns(2)
        for i, c in enumerate(q["c"]):
            choice_text = c['ja'] if mode == "英→日クイズ" else c['en']
            with cols[i % 2]:
                if st.button(choice_text, key=f"b{i}", use_container_width=True):
                    q["ans"] = True
                    is_correct = (str(c['en']).strip() == str(q['t']['en']).strip())
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

        st.write("") 
        for choice in q["c"]:
            is_target = (str(choice['en']).strip() == str(q['t']['en']).strip())
            mark = "✅" if is_target else "・"
            st.write(f"{mark} **{choice['en']}** : {choice['ja']}")
        st.divider()