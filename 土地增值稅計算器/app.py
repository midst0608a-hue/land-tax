import streamlit as st
import pandas as pd
import datetime
import os
import tempfile
from tax_engine import TaxEngine
from pdf_parser import DataParser
from extractor import GeminiExtractor

def parse_gemini_result_to_tax_parcels(gemini_data) -> list:
    import re
    if not isinstance(gemini_data, list):
        gemini_data = [gemini_data]
    parcels = []
    for record in gemini_data:
        # 地號
        land_id = record.get("地號", "")
        if not land_id:
            continue
            
        # 面積
        area_str = str(record.get("面積", "0")).replace(",", "")
        area_match = re.search(r"([\d.]+)", area_str)
        area = float(area_match.group(1)) if area_match else 0.0
        
        # 持分
        holding_str = str(record.get("持分", ""))
        num, den = 1.0, 1.0
        if "分之" in holding_str:
            parts = holding_str.split("分之")
            try:
                den = float(re.sub(r"[^\d]", "", parts[0]))
                num = float(re.sub(r"[^\d]", "", parts[1]))
            except:
                pass
        elif "全部" in holding_str or "1" in holding_str:
            num, den = 1.0, 1.0
            
        # 現值 (公告土地現值)
        present_val_str = str(record.get("現值", "0")).replace(",", "")
        pres_match = re.search(r"([\d.]+)", present_val_str)
        present_value = float(pres_match.group(1)) if pres_match else 0.0
        
        # 前次移轉現值
        orig_str = str(record.get("前次移轉現值", ""))
        orig_year, orig_month, orig_val = 100, 1, 0.0
        orig_match = re.search(r"(\d+)\s*年\s*(\d+)\s*月.*?([\d,.]+)", orig_str)
        if orig_match:
            try:
                orig_year = int(orig_match.group(1))
                orig_month = int(orig_match.group(2))
                orig_val = float(orig_match.group(3).replace(",", ""))
            except:
                pass
        else:
            # 嘗試只抓數值
            val_match = re.search(r"([\d,.]+)", orig_str)
            if val_match:
                try:
                    orig_val = float(val_match.group(1).replace(",", ""))
                except:
                    pass
                    
        parcels.append({
            "id": land_id,
            "owner_name": record.get("所有權人", ""),
            "owner_id": record.get("統一編號", ""),
            "area": area,
            "holding_numerator": num,
            "holding_denominator": den,
            "original_value": orig_val,
            "original_year": orig_year,
            "original_month": orig_month,
            "present_value": present_value,
            "extracted_text": str(record)
        })
    return parcels

st.set_page_config(page_title="台灣不動產全能工作站", page_icon="🏦", layout="wide")

# 套用精美的 CSS 樣式，增加質感
st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6;
    }
    .main footer {visibility: hidden;}
    h1 {
        color: #1E3A8A;
        font-weight: 700;
    }
    h2 {
        color: #2563EB;
        font-weight: 600;
    }
    .stButton>button {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏦 台灣不動產全能工作站")
st.markdown("本系統整合了**土地登記謄本解析與土地增值稅批次試算**，以及**AI 智能謄本與身分證件資料萃取**兩大核心功能。")

# 設定 API Key
if "api_key" not in st.session_state:
    # 優先從 Streamlit Secrets 讀取 (雲端部署推薦)
    secrets_key = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            secrets_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    
    # 次之從系統環境變數讀取
    env_key = os.environ.get("GEMINI_API_KEY", "")
    
    st.session_state.api_key = secrets_key or env_key or ""

with st.sidebar:
    st.header("⚙️ 全域設定")
    # 如果已經有偵測到 API Key (例如來自 Secrets 或環境變數)，在輸入框預設填入並提示
    placeholder = "已從 Secrets 自動載入 API 金鑰" if st.session_state.api_key else "請輸入您的 Google Gemini API Key"
    api_key_input = st.text_input(
        "Google Gemini API Key", 
        type="password", 
        value=st.session_state.api_key,
        placeholder=placeholder
    )
    if api_key_input:
        st.session_state.api_key = api_key_input
        
    st.markdown("---")
    model_options = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]
    st.session_state.selected_model = st.selectbox(
        "🤖 選擇 Gemini 模型",
        options=model_options,
        index=0,
        help="預設為 gemini-2.5-flash，速度快。若檔案較大或同時包含身分證與謄本，建議選擇 gemini-2.5-pro 以提升辨識精度。"
    )
    st.markdown("---")
    st.markdown("### 💡 如何取得 API Key？")
    st.markdown("1. 前往 [Google AI Studio](https://aistudio.google.com/)")
    st.markdown("2. 登入您的 Google 帳號並建立 API key")
    st.markdown("3. 將金鑰貼到上方（或設定於雲端 Secrets 中）")

tab1, tab2 = st.tabs(["🧮 土地增值稅試算", "📄 智能資料萃取"])

# ==========================================
# 分頁一：土地增值稅試算
# ==========================================
with tab1:
    st.markdown("上傳土地登記謄本 (PDF) 與物價指數表 (Excel)，系統將自動擷取所有土地並批次試算土地增值稅（會自動略過建物謄本）。")
    
    # 建立暫存資料夾
    if 'temp_dir' not in st.session_state:
        st.session_state.temp_dir = tempfile.mkdtemp()

    st.header("1. 檔案上傳區")
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        pdf_file = st.file_uploader("📄 上傳土地登記謄本 (PDF)", type=['pdf'], key="tax_pdf_uploader")
    with col_up2:
        excel_file = st.file_uploader("📊 上傳物價指數表 (Excel)", type=['xlsx', 'xls'], key="tax_excel_uploader")
    
    if st.button("🔍 解析文件提取資料", type="primary", use_container_width=True):
        if pdf_file is not None:
            with st.spinner("正在解析 PDF 內容..."):
                # 解決非英文檔名問題：將 PDF 檔案命名為安全的英文暫存檔名
                pdf_ext = pdf_file.name.split(".")[-1].lower()
                pdf_path = os.path.join(st.session_state.temp_dir, f"temp_pdf.{pdf_ext}")
                with open(pdf_path, "wb") as f:
                    f.write(pdf_file.getbuffer())
                
                # 執行批次解析
                extracted_parcels = DataParser.extract_from_pdf(pdf_path)
                
                if len(extracted_parcels) > 0 and "error" in extracted_parcels[0]:
                    st.error(extracted_parcels[0]["error"])
                elif len(extracted_parcels) == 0:
                    # 如果本機解析為 0，且有 API 金鑰，則自動退避至 Gemini 視覺解析
                    if st.session_state.api_key:
                        st.info("⚠️ 偵測到本機解析無文字（可能為掃描檔或加密保護檔），正在啟動 AI 視覺自動解析，請稍候...")
                        current_model = st.session_state.get("selected_model", "gemini-2.5-flash")
                        extractor = GeminiExtractor(api_key=st.session_state.api_key, model_name=current_model)
                        
                        # 呼叫 Gemini 處理 PDF
                        result = extractor.process_pdf(pdf_path)
                        if "error" in result:
                            st.error(f"❌ AI 視覺解析失敗：{result['error']}")
                        else:
                            extracted_parcels = parse_gemini_result_to_tax_parcels(result["data"])
                            if len(extracted_parcels) == 0:
                                st.warning("AI 視覺解析成功，但未能從中辨識出任何土地謄本欄位資訊。")
                            else:
                                st.success(f"✅ AI 視覺解析成功！共找到 {len(extracted_parcels)} 筆土地權利紀錄。")
                    else:
                        st.warning("找不到任何土地謄本資料。本檔案可能為影像掃描檔，請於左側欄填入 Gemini API Key 以啟用 AI 視覺自動解析。")
                else:
                    st.success(f"✅ 解析成功！共找到 {len(extracted_parcels)} 筆土地權利紀錄。")
                
                # 如果成功解析出土地權利紀錄且非錯誤，則初始化 DataFrame
                if len(extracted_parcels) > 0 and "error" not in extracted_parcels[0]:
                    # 初始化 DataFrame 結構
                    df_data = []
                    for p in extracted_parcels:
                        df_data.append({
                            "地號": p["id"],
                            "所有權人": p.get("owner_name", ""),
                            "統一編號": p.get("owner_id", ""),
                            "面積": p["area"],
                            "持分分子": p["holding_numerator"],
                            "持分分母": p["holding_denominator"],
                            "前次現值": p["original_value"],
                            "前次年": p["original_year"],
                            "前次月": p["original_month"],
                            "本次現值": p["present_value"],
                            "自定扣除額": 0.0,
                            "自用住宅": False
                        })
                    st.session_state.parcels_df = pd.DataFrame(df_data)
                    st.session_state.extracted_parcels = extracted_parcels
                    
                    # Debug 面板：讓使用者可以查看原始萃取出的文字
                    with st.expander("🛠️ (除錯用) 查看 PDF 轉出的原始文字"):
                        st.write("這是從 PDF 中解析出的原始文字，供對照與排錯：")
                        for p in extracted_parcels:
                            st.markdown(f"**{p['id']}**")
                            st.text(p["extracted_text"])
                    
                    # 如果有上傳 Excel，使用安全的英文檔名儲存，避免 Pandas 在非英文路徑下報錯
                    if excel_file is not None:
                        excel_ext = excel_file.name.split(".")[-1].lower()
                        excel_path = os.path.join(st.session_state.temp_dir, f"temp_excel.{excel_ext}")
                        with open(excel_path, "wb") as f:
                            f.write(excel_file.getbuffer())
                        st.session_state.excel_path = excel_path
                        st.info("已成功讀取物價指數 Excel 檔案。")
                    else:
                        st.session_state.excel_path = None
                        st.warning("未上傳物價指數表，計算時預設物價指數將為 100% (無調整)")
        else:
            st.error("請先上傳 PDF 檔案！")
    
    st.divider()

    # ==========================================
    # 2. 參數確認與計算區
    # ==========================================
    if 'parcels_df' in st.session_state:
        st.header("2. 參數確認與批次修改")
        st.markdown("您可以直接在下方的表格中修改數字、打勾「自用住宅」，甚至是新增/刪除列（點擊表格邊緣即可操作）。")
        
        # 全局設定 (本次申報年月)
        col_cy, col_cm = st.columns(2)
        today = datetime.datetime.now()
        curr_year = col_cy.number_input("本次申報 (民國年)", value=today.year - 1911, step=1, key="tax_curr_year")
        curr_month = col_cm.number_input("本次申報 (月份)", value=today.month, min_value=1, max_value=12, step=1, key="tax_curr_month")
        
        # 呈現資料編輯器
        edited_df = st.data_editor(
            st.session_state.parcels_df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "自用住宅": st.column_config.CheckboxColumn("自用住宅 (10%)", default=False)
            },
            key="tax_data_editor"
        )
        
        if st.button("🧮 執行批次稅額計算", type="primary", use_container_width=True, key="tax_calc_button"):
            st.divider()
            st.header("3. 計算結果與明細")
            
            total_tax_payable = 0
            results_list = []
            
            # 逐列計算
            for index, row in edited_df.iterrows():
                land_id = row.get("地號", f"第 {index+1} 筆土地")
                area = float(row.get("面積", 0))
                ratio_num = float(row.get("持分分子", 1))
                ratio_den = float(row.get("持分分母", 1))
                orig_val = float(row.get("前次現值", 0))
                orig_year = int(row.get("前次年", 100))
                orig_month = int(row.get("前次月", 1))
                pres_val = float(row.get("本次現值", 0))
                deductions = float(row.get("自定扣除額", 0))
                is_self_use = bool(row.get("自用住宅", False))
                
                # 計算持有年限
                calc_hold_years = max(0, curr_year - orig_year)
                if curr_month < orig_month and calc_hold_years > 0:
                    calc_hold_years -= 1
                    
                # 取得 CPI
                cpi = 100.0
                if st.session_state.get('excel_path'):
                    cpi = DataParser.get_cpi_from_excel(st.session_state.excel_path, orig_year, orig_month)
                    
                if ratio_den == 0:
                    st.error(f"{land_id}: 持分分母不可為 0！已略過計算。")
                    continue
                    
                # 呼叫計算引擎
                result = TaxEngine.calculate_lvit(
                    present_value=pres_val,
                    original_value=orig_val,
                    cpi=cpi,
                    area=area,
                    holding_ratio_numerator=ratio_num,
                    holding_ratio_denominator=ratio_den,
                    deductions=deductions,
                    holding_years=calc_hold_years,
                    is_self_use=is_self_use
                )
                
                total_tax_payable += result['tax_payable']
                results_list.append({
                    "land_id": land_id,
                    "result": result
                })
                
            # 顯示總計
            st.success(f"### 💰 所有土地應納稅額總計： {total_tax_payable:,.0f} 元")
            
            # 顯示各筆明細
            st.markdown("#### 每一筆土地的計算明細")
            for r in results_list:
                land_id = r["land_id"]
                res = r["result"]
                steps = res.get("steps", {})
                
                with st.expander(f"📍 {land_id} - 應納稅額: {res['tax_payable']:,.0f} 元 [{res['tax_rate_level']}]"):
                    col_d1, col_d2 = st.columns(2)
                    
                    with col_d1:
                        st.markdown("**1️⃣ 計算稅基 (按物價調整後原規定地價總額)**")
                        st.latex(r"\text{稅基} = \text{前次現值} \times \frac{\text{CPI}}{100} \times \text{面積} \times \text{持分}")
                        st.write(f"$= {steps.get('original_value_adjusted', 0):,.0f} \\times {steps.get('area', 0)} \\times {steps.get('holding_ratio', 0):.4f}$")
                        st.write(f"$= {res['tax_base']:,.0f}$ 元")
                        
                        st.markdown("**2️⃣ 計算土地漲價總數額**")
                        st.latex(r"\text{漲價總數額} = \text{本次申報現值總額} - \text{稅基} - \text{扣除額}")
                        st.write(f"$= {steps.get('present_value_total', 0):,.0f} - {res['tax_base']:,.0f} - {steps.get('deductions', 0):,.0f}$")
                        st.write(f"$= {res['total_increment']:,.0f}$ 元")
                        
                    with col_d2:
                        st.markdown("**3️⃣ 判斷漲價倍數與稅率**")
                        st.latex(r"\text{漲價倍數} = \frac{\text{漲價總數額}}{\text{稅基}}")
                        st.write(f"$= {res['increment_ratio']:.2f}$ 倍")
                        st.write(f"👉 適用級距：**{res['tax_rate_level']}**")
                        
                        st.markdown("**4️⃣ 最終應納稅額**")
                        st.write(f"👉 持有年限：**{steps.get('holding_years', 0)} 年**")
                        st.info(f"**最終稅額： {res['tax_payable']:,.0f} 元**")

# ==========================================
# 分頁二：智能資料萃取 (OCR)
# ==========================================
with tab2:
    st.header("📄 謄本與身分證自動萃取神器")
    st.markdown("上傳紙本掃描圖檔、PDF、或身分證件，AI 將自動辨識所有權人、地址、統編、建號、公告現值等資訊並輸出純文字。")
    
    if not st.session_state.api_key:
        st.warning("⚠️ 請先在左側欄輸入您的 Google Gemini API Key 或設定 Secrets 才能開啟此功能！")
    else:
        uploaded_file2 = st.file_uploader("請上傳圖檔或 PDF", type=["pdf", "jpg", "jpeg", "png"], key="extractor_up")
        if uploaded_file2 is not None:
            # 建立快取鍵值
            current_file_key = f"{uploaded_file2.name}_{uploaded_file2.size}"
            
            # 檢查是否已有該檔案的快取結果
            cached_key = st.session_state.get("extractor_file_key")
            cached_result = st.session_state.get("extractor_result")
            cached_model = st.session_state.get("extractor_model_used")
            
            # 模型選擇狀態
            current_model = st.session_state.get("selected_model", "gemini-2.5-flash")
            
            # 判斷是否需要重新執行 (檔案變更，或是模型變更，或是快取不存在)
            need_run = False
            if cached_key != current_file_key or cached_result is None or cached_model != current_model:
                need_run = True
                
            # 提供手動重新萃取的按鈕與模型狀態提示
            col1, col2 = st.columns([2, 8])
            with col1:
                if st.button("🔄 重新萃取", use_container_width=True):
                    need_run = True
            with col2:
                st.markdown(f"<div style='padding-top: 5px; color: #555;'><small>目前使用模型：<code>{current_model}</code></small></div>", unsafe_allow_html=True)
                
            if need_run:
                if 'temp_dir' not in st.session_state:
                    st.session_state.temp_dir = tempfile.mkdtemp()
                    
                # 解決非英文檔名問題：重新命名為安全檔名 extract_temp.{ext}，避免 Gemini API 上傳或讀取時編碼錯誤
                file_ext = uploaded_file2.name.split(".")[-1].lower()
                safe_filename = f"extract_temp.{file_ext}"
                file_path = os.path.join(st.session_state.temp_dir, safe_filename)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file2.getbuffer())
                
                st.info("🤖 AI 正在努力閱讀並萃取資料中，請稍候 (約需 5~15 秒)...")
                
                # 初始化 extractor 並帶入選擇的模型
                extractor = GeminiExtractor(
                    api_key=st.session_state.api_key,
                    model_name=current_model
                )
                
                with st.spinner("解析中..."):
                    if file_ext == "pdf":
                        result = extractor.process_pdf(file_path)
                    else:
                        result = extractor.process_image(file_path)
                        
                # 只有當沒有發生 429 或其他網路暫時性錯誤時，才快取結果
                if "error" in result and ("429" in result["error"] or "RESOURCE_EXHAUSTED" in result["error"]):
                    # 429 不快取
                    pass
                else:
                    st.session_state.extractor_file_key = current_file_key
                    st.session_state.extractor_result = result
                    st.session_state.extractor_model_used = current_model
            else:
                # 從快取讀取
                result = cached_result
                
            if "error" in result:
                st.error(f"❌ 發生錯誤：{result['error']}")
                if "raw" in result:
                    with st.expander("查看原始 AI 回覆"):
                        st.text(result["raw"])
            else:
                st.success("✅ 萃取成功！")
                data_list = result["data"]
                if not isinstance(data_list, list):
                    data_list = [data_list]
                    
                if len(data_list) == 0:
                    st.warning("AI 沒有在這份文件中找到相符的資料。")
                else:
                    formatted_text = ""
                    for i, record in enumerate(data_list):
                        formatted_text += f"【紀錄 {i+1}】\n"
                        
                        # 定義謄本/證件常見欄位顯示順序
                        keys_order = [
                            "地號", "建號", "門牌", "面積", "持分", "現值", "所有權人", "統一編號", "出生年月日",
                            "主要用途", "主要建材", "建築完成日期", "層次與面積", 
                            "主建物總面積", "附屬建物用途與面積", "前次移轉現值", "歷次取得範圍", "地址"
                        ]
                        
                        for key in keys_order:
                            if key in record and record[key]:
                                formatted_text += f"{key}：{record[key]}\n"
                                
                        for key, value in record.items():
                            if key not in keys_order and value:
                                formatted_text += f"{key}：{value}\n"
                                
                        formatted_text += "\n"
                        
                    st.markdown("### 📋 萃取結果 (可直接複製)")
                    st.code(formatted_text.strip(), language="text")
                    st.markdown("*(小提示：您可以直接點擊上方文字框右上角的「複製」按鈕)*")
