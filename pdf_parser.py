import pdfplumber
import re
import pandas as pd
import datetime

class DataParser:
    @staticmethod
    def extract_from_pdf(pdf_path: str) -> list:
        """
        從土地謄本 PDF 中擷取多筆土地的必要欄位
        回傳 List of Dicts
        """
        # 儲存每一筆地號對應的完整純文字
        parcel_texts = {}
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if not page_text:
                        continue
                        
                    lines = page_text.split('\n')
                    
                    # 檢查前 5 行尋找標頭的地號 (例如: 西屯區順和段 0151-0000地號)
                    # 避免抓到內文的參考地號
                    header_land_id = None
                    for line in lines[:5]:
                        # 找尋以地號結尾的字串 (略過建號)
                        if "建號" in line:
                            break # 如果是建物謄本，直接略過此頁
                            
                        id_match = re.search(r"([^\n]*?段[^\n]*?地號)", line)
                        if id_match:
                            header_land_id = id_match.group(1).strip()
                            break
                            
                    # 如果這頁有地號，且不是建物謄本
                    if header_land_id:
                        if header_land_id not in parcel_texts:
                            parcel_texts[header_land_id] = ""
                        parcel_texts[header_land_id] += page_text + "\n"
                        
        except Exception as e:
            return [{"error": f"無法讀取 PDF: {str(e)}"}]
            
        results = []
        
        # 針對每一筆組合好的完整地號文字進行正規表達式萃取
        for land_id, full_text in parcel_texts.items():
            # 確保這是土地謄本 (有可能頁面標頭有地號，但其實是建物謄本的標示部，不過我們上面已經擋掉「建號」了)
            if "建物標示部" in full_text:
                continue
                
            data = {
                "id": land_id,
                "area": 0.0,
                "holding_numerator": 1,
                "holding_denominator": 1,
                "original_value": 0.0,
                "original_year": 100,
                "original_month": 1,
                "present_value": 0.0,
                "present_year": datetime.datetime.now().year - 1911,
                "present_month": 1,
                "extracted_text": full_text
            }
            
            # 1. 面積 (整筆土地共用)
            area = 0.0
            area_match = re.search(r"面\s*積[：:]?[^\d]*([\d\,\.]+)\s*平方公尺", full_text)
            if area_match:
                area = float(area_match.group(1).replace(",", ""))
                
            # 4. 公告土地現值 (整筆土地共用)
            present_year = datetime.datetime.now().year - 1911
            present_month = 1
            present_value = 0.0
            curr_match = re.search(r"民國(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*公告土地現值[：:]?[^\d]*([\d\,\.]+)\s*元", full_text)
            if curr_match:
                present_year = int(curr_match.group(1))
                present_month = int(curr_match.group(2))
                present_value = float(curr_match.group(3).replace(",", ""))
            else:
                curr_match_fallback = re.search(r"公告土地現值[：:]?[^\d]*([\d\,\.]+)\s*元", full_text)
                if curr_match_fallback:
                    present_value = float(curr_match_fallback.group(1).replace(",", ""))

            # 在切塊前，先移除「他項權利部」以後的所有內容，避免抓到抵押權人的持分與次序
            if "他項權利部" in full_text:
                full_text = full_text.split("他項權利部")[0]

            # 針對這塊土地，可能有「多個權利範圍」(例如多個持分或不同前次移轉年月)
            # 實務上每一筆權利範圍前面會有「登記次序」
            ownership_chunks = re.split(r"登記次序[：:]?", full_text)
            if len(ownership_chunks) <= 1:
                ownership_chunks = [full_text]
                
            record_index = 1
            valid_records_in_this_land = 0
            
            for chunk in ownership_chunks:
                # 2. 權利範圍/持分
                ratio_match = re.search(r"權利範圍[：:]?[^\d]*([\d\,]+)\s*分之\s*([\d\,]+)", chunk)
                holding_denominator = 1
                holding_numerator = 1
                found_ratio = False
                
                if ratio_match:
                    holding_denominator = float(ratio_match.group(1).replace(",", ""))
                    holding_numerator = float(ratio_match.group(2).replace(",", ""))
                    found_ratio = True
                elif re.search(r"權利範圍[：:]?[^\d]*全部", chunk):
                    found_ratio = True
                    
                # 3. 前次移轉現值或原規定地價
                orig_match = re.search(r"前次移轉現值或原規定地價[：:]?[\s\S]{0,100}?(\d{2,3})\s*年\s*(\d{1,2})\s*月[^\d]*?([\d\,\.]+)\s*元", chunk)
                original_year = 100
                original_month = 1
                original_value = 0.0
                found_orig = False
                
                if orig_match:
                    original_year = int(orig_match.group(1))
                    original_month = int(orig_match.group(2))
                    original_value = float(orig_match.group(3).replace(",", ""))
                    found_orig = True
                    
                # 5. 所有權人與統一編號 (處理所有字元之間的空格，包含 所、有 之間)
                owner_match = re.search(r"所\s*有\s*權\s*人\s*[：:]?\s*([^\n]+)", chunk)
                owner_name = owner_match.group(1).replace(" ", "").replace("　", "").strip() if owner_match else ""
                
                # 統一編號通常是英文數字跟星號組成
                id_num_match = re.search(r"統\s*一\s*編\s*號\s*[：:]?\s*([A-Za-z0-9\*\s]+)", chunk)
                owner_id = id_num_match.group(1).replace(" ", "").replace("　", "").strip() if id_num_match else ""
                
                # 只有當這個 chunk 確實有找到持分或前次現值時，才視為一筆獨立的權利紀錄
                # 因為第一個 chunk 通常是土地標示部，不含權利範圍，會被自動略過
                if found_ratio or found_orig:
                    valid_records_in_this_land += 1
                    # 如果一筆地號只有一個權利範圍，就不加後綴；如果有多個，加上「(權利紀錄 X)」來區分
                    display_id = land_id if len(ownership_chunks) <= 2 else f"{land_id} (權利紀錄 {valid_records_in_this_land})"
                    
                    data = {
                        "id": display_id,
                        "owner_name": owner_name,
                        "owner_id": owner_id,
                        "area": area,
                        "holding_numerator": holding_numerator,
                        "holding_denominator": holding_denominator,
                        "original_value": original_value,
                        "original_year": original_year,
                        "original_month": original_month,
                        "present_value": present_value,
                        "present_year": present_year,
                        "present_month": present_month,
                        "extracted_text": chunk
                    }
                    results.append(data)
                    record_index += 1
                    
            # 防呆：如果在切塊過程中什麼都沒抓到，至少回傳一個預設物件，以免整個土地消失
            if valid_records_in_this_land == 0:
                data = {
                    "id": land_id,
                    "owner_name": "",
                    "owner_id": "",
                    "area": area,
                    "holding_numerator": 1,
                    "holding_denominator": 1,
                    "original_value": 0.0,
                    "original_year": 100,
                    "original_month": 1,
                    "present_value": present_value,
                    "present_year": present_year,
                    "present_month": present_month,
                    "extracted_text": full_text
                }
                results.append(data)
            
        return results

    @staticmethod
    def get_cpi_from_excel(excel_path: str, target_year: int, target_month: int) -> float:
        """
        從 Excel 讀取對應年月之物價指數
        支援無固定標題列，自動搜尋符合年份的橫列
        """
        try:
            # 不預設 header，避免標題列在第 2 或 3 行造成錯位
            df = pd.read_excel(excel_path, header=None)
            
            # 逐列搜尋
            for idx, row in df.iterrows():
                year_col_idx = -1
                
                # 在前幾欄中尋找是否有符合的「年份」數字
                for col_idx in range(min(3, len(row))):
                    val = row.iloc[col_idx]
                    if pd.notna(val):
                        try:
                            # 容忍 '60', '60.0', '60年' 等格式
                            val_str = str(val).strip().replace('年', '').replace('民國', '')
                            if int(float(val_str)) == target_year:
                                year_col_idx = col_idx
                                break
                        except:
                            pass
                
                if year_col_idx != -1:
                    # 找到了年份所在的列與欄位！
                    # 假設月份是依序排列在年份右邊：年 | 1月 | 2月 ... | 11月
                    # 所以目標月份的欄位索引會是：年份欄位索引 + target_month
                    target_col_idx = year_col_idx + target_month
                    
                    if target_col_idx < len(row):
                        cpi_val = row.iloc[target_col_idx]
                        try:
                            return float(cpi_val)
                        except:
                            pass
                            
            return 100.0
            
        except Exception as e:
            print(f"讀取物價指數 Excel 發生錯誤: {e}")
            return 100.0
