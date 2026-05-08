import streamlit as st
import pandas as pd
import datetime
from tax_engine import TaxEngine
from pdf_parser import DataParser
import os
import tempfile

st.set_page_config(page_title="台灣土地增值稅計算器", page_icon="🏦", layout="wide")

st.title("🏦 台灣土地增值稅 (LVIT) 批次試算系統")
st.markdown("上傳土地謄本 (PDF) 與物價指數表 (Excel)，系統將自動擷取所有土地並批次試算土地增值稅。 (自動略過建物謄本)")

# 建立暫存資料夾
if 'temp_dir' not in st.session_state:
    st.session_state.temp_dir = tempfile.mkdtemp()

# ==========================================
# 1. 檔案上傳與解析區
# ==========================================
st.header("1. 檔案上傳區")
col_up1, col_up2 = st.columns(2)
with col_up1:
    pdf_file = st.file_uploader("📄 上傳土地登記謄本 (PDF)", type=['pdf'])
with col_up2:
    excel_file = st.file_uploader("📊 上傳物價指數表 (Excel)", type=['xlsx', 'xls'])

if st.button("🔍 解析文件提取資料", type="primary"):
    if pdf_file is not None:
        with st.spinner("正在解析 PDF 內容..."):
            pdf_path = os.path.join(st.session_state.temp_dir, "temp.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_file.getbuffer())
            
            # 執行批次解析
            extracted_parcels = DataParser.extract_from_pdf(pdf_path)
            
            if len(extracted_parcels) > 0 and "error" in extracted_parcels[0]:
                st.error(extracted_parcels[0]["error"])
            elif len(extracted_parcels) == 0:
                st.warning("找不到任何土地謄本資料。請確認檔案格式或是否僅包含建物謄本。")
            else:
                st.success(f"✅ 解析成功！共找到 {len(extracted_parcels)} 筆土地謄本。")
                
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
                    st.write("請將下方的文字截圖或複製給 AI，這樣 AI 就能知道文字到底是怎麼排列的！")
                    for p in extracted_parcels:
                        st.markdown(f"**{p['id']}**")
                        st.text(p["extracted_text"])
                
                # 如果有上傳 Excel，一併處理
                if excel_file is not None:
                    excel_path = os.path.join(st.session_state.temp_dir, excel_file.name)
                    with open(excel_path, "wb") as f:
                        f.write(excel_file.getbuffer())
                    st.session_state.excel_path = excel_path
                    st.info("已成功讀取物價指數 Excel 檔案。")
                else:
                    st.session_state.excel_path = None
                    st.warning("未上傳物價指數表，計算時預設指數將為 100% (無調整)")
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
    curr_year = col_cy.number_input("本次申報 (民國年)", value=today.year - 1911, step=1)
    curr_month = col_cm.number_input("本次申報 (月份)", value=today.month, min_value=1, max_value=12, step=1)
    
    # 呈現資料編輯器
    edited_df = st.data_editor(
        st.session_state.parcels_df, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "自用住宅": st.column_config.CheckboxColumn("自用住宅 (10%)", default=False)
        }
    )
    
    if st.button("🧮 執行批次稅額計算", type="primary", use_container_width=True):
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
