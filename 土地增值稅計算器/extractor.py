import os
import json
import time
from google import genai
from google.genai import types

class GeminiExtractor:
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def _call_gemini_with_retry(self, client, model: str, contents: list, max_retries: int = 5) -> str:
        """
        呼叫 Gemini API，並在遭遇 503, 429 或其他暫時性服務不可用/超時的錯誤時，
        進行指數退避 (exponential backoff) 重試。
        """
        import random
        
        delay = 2.0  # 初始等待 2 秒
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents
                )
                return response.text
            except Exception as e:
                last_exception = e
                err_msg = str(e).upper()
                
                # 判斷是否為暫時性錯誤 (如: 503 Unavailable, 429 Rate Limit/Resource Exhausted, 或者包含 high demand 等說明)
                is_transient = any(
                    indicator in err_msg 
                    for indicator in [
                        "503", "429", "RESOURCE_EXHAUSTED", "UNAVAILABLE", 
                        "HIGH DEMAND", "TEMPORARY", "SPIKE", "OVERLOADED", 
                        "RATE_LIMIT", "QUOTA"
                    ]
                )
                
                # 如果不是明確的暫時性錯誤，且已經試了 2 次，就不再浪費時間重試，直接拋出
                if not is_transient and attempt >= 2:
                    raise e
                
                if attempt < max_retries - 1:
                    # 加入隨機擾動 (jitter) 避免多個請求同時重試
                    sleep_time = delay + random.uniform(0, 1)
                    time.sleep(sleep_time)
                    delay *= 2  # 指數級增加等待時間
                else:
                    break
                    
        raise last_exception

    def _get_prompt(self):
        return """
        你是一個專業的台灣不動產與身分證件資料萃取助理。
        請分析使用者提供的文件 (可能是土地謄本、建物謄本，或是身分證件)。
        
        請從文件中萃取以下所有欄位：
        1. 地號 (如果是土地謄本)
        2. 面積 (包含單位，如平方公尺)
        3. 持分 (權利範圍)
        4. 現值 (請明確抓取「公告土地現值」，請勿抓取「當期申報地價」)
        5. 所有權人 (姓名)
        6. 統一編號 (身分證字號或統編)
        7. 前次移轉現值 (必須包含年月與價格。如果同一個地號有多筆前次移轉紀錄，請分別列出，例如：「109年5月：13,000元／平方公尺；111年2月：15,000元／平方公尺」)
        8. 歷次取得範圍 (若有多筆對應前次移轉的持分取得範圍，也請分別列出)
        9. 地址 (包含身分證上的戶籍地址或謄本上的住址)
        
        【特別指示：針對建物謄本】
        如果這是一份「建物謄本」，除了抓取原有資訊外，請務必一併抓取「建物標示部」的內容。請確保自行在 JSON 內新增並包含以下欄位：
        - 建號
        - 門牌
        - 主要用途
        - 主要建材
        - 建築完成日期
        - 層次與面積 (請將各層次及其對應的面積詳細列出)
        - 主建物總面積 (【重要計算邏輯】除明確標示為「附屬建物」外，其餘所有層次之面積必須全部加總，作為正確的主建物總面積)
        - 附屬建物用途與面積 (若有標示為附屬建物，請務必同時抓取其「用途性質」與對應的「面積」，例如：「陽台：10.5平方公尺；雨遮：2.0平方公尺」。請獨立列出每一項附屬建物，切勿只給總和數字，也切勿計入主建物總面積)
        請將這些建物標示部的資訊與所有權人等資訊「整合在同一個紀錄物件中」，確保內容完整不遺漏。
        
        如果一份文件中有多筆權利紀錄 (例如同一個地號有多個持分人)，請你把「每一筆紀錄」都當成一個獨立的物件。
        
        請以嚴格的 JSON 陣列 (JSON Array) 格式回傳，不要包含任何 Markdown 標記 (如 ```json) 或是其他多餘的說明文字。
        如果某個欄位在文件中找不到，請留空字串 ""。
        
        JSON 格式範例：
        [
            {
                "地號": "西屯區順和段 0151-0000",
                "面積": "679.07 平方公尺",
                "持分": "10000分之384",
                "現值": "4,160.0元／平方公尺",
                "所有權人": "吳林桂花",
                "統一編號": "N201807918",
                "前次移轉現值": "109年5月：13,000.0元／平方公尺",
                "歷次取得範圍": "10000分之384",
                "地址": "台中市西屯區協和里..."
            }
        ]
        """

    def process_file(self, file_path: str, mime_type: str):
        uploaded_file = None
        temp_ascii_path = None
        try:
            client = genai.Client(api_key=self.api_key)
            prompt = self._get_prompt()
            
            # Check if filename contains non-ASCII characters to avoid google-genai SDK header encoding bug
            filename = os.path.basename(file_path)
            try:
                filename.encode('ascii')
                upload_path = file_path
            except UnicodeEncodeError:
                import shutil
                import tempfile
                ext = os.path.splitext(file_path)[1]
                temp_dir = os.path.dirname(file_path) or tempfile.gettempdir()
                temp_ascii_path = os.path.join(temp_dir, f"temp_upload_ascii_{int(time.time())}{ext}")
                shutil.copy2(file_path, temp_ascii_path)
                upload_path = temp_ascii_path

            # 使用 File API 上傳檔案
            uploaded_file = client.files.upload(
                file=upload_path, 
                config={'mime_type': mime_type}
            )
            
            # 等待檔案處理完成 (變成 ACTIVE 狀態)
            while True:
                file_info = client.files.get(name=uploaded_file.name)
                state_str = str(file_info.state)
                if "ACTIVE" in state_str:
                    break
                elif "FAILED" in state_str:
                    return {"error": f"API 檔案處理失敗 (狀態: {state_str})，請嘗試換一個檔案。"}
                time.sleep(2)
            
            # 直接使用 gemini-2.5-flash (因 1.5 版已退役)
            try:
                response_text = self._call_gemini_with_retry(
                    client=client,
                    model='gemini-2.5-flash',
                    contents=[file_info, prompt]
                )
            except Exception as e_flash:
                # 不再盲目降級到 1.5-pro，直接回傳真實的錯誤訊息
                return {"error": f"Gemini 2.5 Flash 生成內容時發生錯誤：{str(e_flash)}"}
                
            return self._parse_response(response_text)
            
        except Exception as e:
            return {"error": f"API 發生錯誤：請確認 API Key 是否有效。詳細錯誤：{str(e)}"}
        finally:
            # 清理：無論成功或失敗，都盡可能刪除雲端上的暫存檔案
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass
            # 清理 ASCII 暫存檔案
            if temp_ascii_path and os.path.exists(temp_ascii_path):
                try:
                    os.remove(temp_ascii_path)
                except Exception:
                    pass

    def process_image(self, image_path: str):
        """處理單張圖片 (如身分證 JPG/PNG)"""
        ext = image_path.split('.')[-1].lower()
        mime = f"image/{ext}" if ext in ["png", "jpeg"] else "image/jpeg"
        return self.process_file(image_path, mime)

    def process_pdf(self, pdf_path: str):
        """處理 PDF 檔案 (如電子謄本或掃描謄本)"""
        return self.process_file(pdf_path, "application/pdf")

    def _parse_response(self, text: str):
        """解析 Gemini 回傳的 JSON 文字"""
        try:
            # 嘗試清除可能的 Markdown 標記
            clean_text = text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
                
            clean_text = clean_text.strip()
            data = json.loads(clean_text)
            return {"success": True, "data": data}
        except json.JSONDecodeError:
            return {"error": "無法解析 AI 的回覆格式，請重新嘗試。", "raw": text}

    def process_review(self, doc_path: str, doc_mime: str, case_desc: str, manual_path: str = None, manual_mime: str = None):
        """上傳要審查的文件以及(選填的)審查手冊，根據案件描述與手冊規範進行比對與審核"""
        uploaded_doc = None
        uploaded_manual = None
        temp_doc_ascii = None
        temp_manual_ascii = None
        try:
            client = genai.Client(api_key=self.api_key)
            import shutil
            import tempfile
            
            # Ensure doc_path is ASCII-safe to avoid google-genai SDK header encoding bug
            doc_filename = os.path.basename(doc_path)
            try:
                doc_filename.encode('ascii')
                upload_doc_path = doc_path
            except UnicodeEncodeError:
                ext = os.path.splitext(doc_path)[1]
                temp_dir = os.path.dirname(doc_path) or tempfile.gettempdir()
                temp_doc_ascii = os.path.join(temp_dir, f"temp_doc_ascii_{int(time.time())}{ext}")
                shutil.copy2(doc_path, temp_doc_ascii)
                upload_doc_path = temp_doc_ascii

            # 1. 上傳要審查的文件 (公契/申請書)
            uploaded_doc = client.files.upload(
                file=upload_doc_path, 
                config={'mime_type': doc_mime}
            )
            
            # 等待檔案處理完成
            while True:
                doc_info = client.files.get(name=uploaded_doc.name)
                state_str = str(doc_info.state)
                if "ACTIVE" in state_str:
                    break
                elif "FAILED" in state_str:
                    return {"error": f"審查文件處理失敗 (狀態: {state_str})"}
                time.sleep(2)
                
            contents = [doc_info]
            
            # 2. 上傳自訂審查手冊 (選填)
            if manual_path and manual_mime:
                # Ensure manual_path is ASCII-safe
                manual_filename = os.path.basename(manual_path)
                try:
                    manual_filename.encode('ascii')
                    upload_manual_path = manual_path
                except UnicodeEncodeError:
                    ext = os.path.splitext(manual_path)[1]
                    temp_dir = os.path.dirname(manual_path) or tempfile.gettempdir()
                    temp_manual_ascii = os.path.join(temp_dir, f"temp_manual_ascii_{int(time.time())}{ext}")
                    shutil.copy2(manual_path, temp_manual_ascii)
                    upload_manual_path = temp_manual_ascii

                uploaded_manual = client.files.upload(
                    file=upload_manual_path, 
                      def process_contract_extraction(self, 
                                   land_doc_path: str = None, land_doc_mime: str = None,
                                   building_doc_paths: list = None, building_doc_mimes: list = None,
                                   seller_id_paths: list = None, seller_id_mimes: list = None,
                                   buyer_id_paths: list = None, buyer_id_mimes: list = None,
                                   seller_id_path: str = None, seller_id_mime: str = None,
                                   buyer_id_path: str = None, buyer_id_mime: str = None,
                                   doc_paths: list = None, doc_mimes: list = None):
        """
        上傳多個檔案（謄本及身分證件），利用 Gemini 2.5 Flash 進行資料萃取，對齊公契與報稅所需欄位。
        """
        client = genai.Client(api_key=self.api_key)
        uploaded_files = []
        temp_ascii_paths = []
        contents = []
        
        # 動態建立要上傳與處理的檔案清單
        files_to_process = []
        
        if doc_paths is not None:
            # 優先使用整合上傳的檔案清單
            for idx, (path, mime) in enumerate(zip(doc_paths, doc_mimes)):
                if path and mime:
                    files_to_process.append((f"doc_{idx}", path, mime))
        else:
            # 向後相容單一類別的舊參數
            if seller_id_paths is None:
                seller_id_paths = [seller_id_path] if seller_id_path else []
            if seller_id_mimes is None:
                seller_id_mimes = [seller_id_mime] if seller_id_mime else []
            if buyer_id_paths is None:
                buyer_id_paths = [buyer_id_path] if buyer_id_path else []
            if buyer_id_mimes is None:
                buyer_id_mimes = [buyer_id_mime] if buyer_id_mime else []
            if building_doc_paths is None:
                building_doc_paths = []
            if building_doc_mimes is None:
                building_doc_mimes = []
                
            if land_doc_path and land_doc_mime:
                files_to_process.append(("land_doc", land_doc_path, land_doc_mime))
                
            for idx, (path, mime) in enumerate(zip(building_doc_paths, building_doc_mimes)):
                if path and mime:
                    files_to_process.append((f"building_doc_{idx}", path, mime))
                
            for idx, (path, mime) in enumerate(zip(seller_id_paths, seller_id_mimes)):
                if path and mime:
                    files_to_process.append((f"seller_id_{idx}", path, mime))
                    
            for idx, (path, mime) in enumerate(zip(buyer_id_paths, buyer_id_mimes)):
                if path and mime:
                    files_to_process.append((f"buyer_id_{idx}", path, mime))
            
        try:
            import shutil
            import tempfile
            
            for key, path, mime in files_to_process:
                if path and mime:
                    filename = os.path.basename(path)
                    try:
                        filename.encode('ascii')
                        upload_path = path
                    except UnicodeEncodeError:
                        ext = os.path.splitext(path)[1]
                        temp_dir = os.path.dirname(path) or tempfile.gettempdir()
                        temp_ascii = os.path.join(temp_dir, f"temp_{key}_ascii_{int(time.time())}{ext}")
                        shutil.copy2(path, temp_ascii)
                        temp_ascii_paths.append(temp_ascii)
                        upload_path = temp_ascii
                        
                    # 上傳檔案
                    uploaded_file = client.files.upload(
                        file=upload_path,
                        config={'mime_type': mime}
                    )
                    uploaded_files.append(uploaded_file)
                    
                    # 等待 ACTIVE
                    while True:
                        file_info = client.files.get(name=uploaded_file.name)
                        state_str = str(file_info.state)
                        if "ACTIVE" in state_str:
                            break
                        elif "FAILED" in state_str:
                            return {"error": f"檔案 {key} 處理失敗 (狀態: {state_str})"}
                        time.sleep(2)
                        
                    contents.append(file_info)
            
            # 如果沒有任何上傳文件，直接返回空欄位
            if not contents:
                return {
                    "success": True,
                    "data": {
                        "people": [],
                        "lands": [],
                        "buildings": []
                    }
                }
                
            prompt = """
            你是一個專業的台灣地政登記案件資料萃取助理。
            請從上傳的所有文件中（包含土地登記謄本、建物登記謄本、身分證影本等），精確萃取所有相關人、土地與建物資訊，以供填寫「土地建物所有權移轉契約書 (公契)」、「土地登記申請書」與「登記清冊」之用。
            
            【特別指示：當事人身分證與謄本辨識】
            1. 請完整辨識並萃取所有文件（包含身分證件與謄本）中出現的所有自然人，將每個人獨立作為一個物件，填入 `people` 陣列中。
            2. 請盡可能辨識每個人的姓名、身分證統一編號、出生年月日與戶籍地址。
            3. 如果文件中含有前次移轉現值申報資訊（通常出現在土地登記謄本之所有權部），請擷取該所有權人取得該土地時的「前次移轉年月」（民國格式，如 10704，代表107年4月）、「前次移轉現值」（單價，僅數字）、以及取得該持分時的「持分分子/分母」。
            
            【特別指示：針對建物登記謄本】
            如果上傳的檔案包含「建物登記謄本」，請務必擷取以下資訊並填入 `buildings` 陣列中：
            - 建號：例如「183」或「00183-000」
            - 門牌：例如「龍井區三港路水裡港巷68之16號」
            - 主要用途：例如「住家用」或「商業用」
            - 基地坐落地號：例如「田水段 859-23地號」
            - 層次與面積：各樓層面積，例如「一層 43.30, 二層 56.46, 騎樓 15.05... 共計 124.71」
            - 附屬建物：用途與面積，例如「陽台 2.42」
            - 移轉權利範圍：持分分子/分母，例如「1/1」
            - 房屋現值（評定現值）：如果文件中含有課稅現值或房屋評定現值（若無則為 0）
            - 備註：例如「公同共有」或空白
            
            請以嚴格的 JSON 格式回傳，且必須符合以下 JSON 結構：
            {
              "people": [
                {
                  "name": "姓名",
                  "id_number": "統一編號（身分證字號）",
                  "birthday": "出生年月日，請轉換為民國年格式，例如：民國50年10月12日",
                  "address": "戶籍地址",
                  "prev_year_month": "前次移轉年月（民國格式，如 10704，若沒有則預設 10704）",
                  "prev_value_per_sqm": "前次移轉現值，僅數字（元/平方公尺，若沒有則預設 19000）",
                  "prev_holding_numerator": "前次移轉持分分子，僅數字（若沒有則預設 1）",
                  "prev_holding_denominator": "前次移轉持分分母，僅數字（若沒有則預設 2）"
                }
              ],
              "lands": [
                {
                  "section": "地段名稱，例如：順和段",
                  "land_number": "地號，例如：0151-0000",
                  "area": "面積，僅填寫數字（單位為平方公尺），例如：679.07",
                  "holding_numerator": "移轉權利範圍（持分分子），僅數字，例如 1",
                  "holding_denominator": "移轉權利範圍（持分分母），僅數字，例如 1",
                  "value_per_sqm": "公告地段現值，僅填寫數字，例如：4160"
                }
              ],
              "buildings": [
                {
                  "building_number": "建號，例如：183",
                  "door_number": "門牌地址，例如：龍井區三港路水裡港巷68之16號",
                  "land_number": "基地坐落地號，例如：田水段 859-23地號",
                  "area_details": "層次面積明細，例如：一層 43.30, 二層 56.46, 騎樓 15.05",
                  "total_area": "主建物總面積，僅填寫數字，例如：124.7",
                  "attached_area": "附屬建物明細，例如：陽台 2.42",
                  "holding_numerator": "移轉持分分子，僅數字，例如：1",
                  "holding_denominator": "移轉持分分母，僅數字，例如：1",
                  "value_per_sqm": "評定現值，僅填寫數字，若無則填 0",
                  "remarks": "備註，例如：公同共有"
                }
              ]
            }
            
            請不要包含 any Markdown 標記 (如 ```json) 或是其他多餘的說明文字。
            如果某個檔案未提供，或某個欄位在文件中確實找不到，請填寫空字串 ""。
            """
            
            contents.append(prompt)
            
            # 呼叫 Gemini 2.5 Flash
            response_text = self._call_gemini_with_retry(
                client=client,
                model='gemini-2.5-flash',
                contents=contents
            )
            
            return self._parse_response(response_text)
            
        except Exception as e:
            return {"error": f"資料萃取失敗：{str(e)}"}�不同的身分證，屬於「買受人（權利人）/ 受贈人」。
               - 若未上傳土地謄本，僅有身分證，請直接依據上傳類別（出賣人證件為 sellers，買受人證件為 buyers）進行填寫。
            4. 前次移轉現值申報資訊 (出賣人)：
               - 請從土地登記謄本之所有權部（「前次移轉現值」或「歷次取得權利範圍」欄位）中，擷取該出賣人（所有權人）取得該土地時的「前次移轉年月」（格式如民國年月：10704，代表107年4月）、「前次移轉現值（單價）」（格式如：19000）、以及取得該持分時的「持分分子/分母」。
            
            【特別指示：針對建物登記謄本】
            如果上傳的檔案包含「建物登記謄本」，請務必擷取以下資訊並填入 `buildings` 陣列中：
            - 建號：例如「183」或「00183-000」
            - 門牌：例如「龍井區三港路水裡港巷68之16號」
            - 主要用途：例如「住家用」或「商業用」
            - 基地坐落地號：例如「田水段 859-23地號」
            - 層次與面積：各樓層面積，例如「一層 43.30, 二層 56.46, 騎樓 15.05... 共計 124.71」
            - 附屬建物：用途與面積，例如「陽台 2.42」
            - 移轉權利範圍：持分分子/分母，例如「1/1」
            - 房屋現值（評定現值）：如果文件中含有課稅現值或房屋評定現值（若無則為 0）
            - 備註：例如「公同共有」或空白
            
            請以嚴格的 JSON 格式回傳，且必須符合以下 JSON 結構：
            {
              "sellers": [
                {
                  "name": "出賣人/義務人姓名",
                  "id_number": "出賣人統一編號（身分證字號）",
                  "birthday": "出賣人出生年月日，請轉換為民國年格式，例如：民國50年10月12日",
                  "address": "出賣人戶籍地址",
                  "prev_year_month": "前次移轉年月（民國格式，如 10704，若沒有則預設 10704）",
                  "prev_value_per_sqm": "前次移轉現值，僅數字（元/平方公尺，若沒有則預設 19000）",
                  "prev_holding_numerator": "前次移轉持分分子，僅數字（若沒有則預設 1）",
                  "prev_holding_denominator": "前次移轉持分分母，僅數字（若沒有則預設 2）"
                }
              ],
              "buyers": [
                {
                  "name": "買受人/權利人姓名",
                  "id_number": "買受人統一編號（身分證字號）",
                  "birthday": "買受人出生年月日，請轉換為民國年格式，例如：民國80年1月5日",
                  "address": "買受人戶籍地址",
                  "holding_numerator": "移轉權利範圍（持分分子），僅數字，例如 1",
                  "holding_denominator": "移轉權利範圍（持分分母），僅數字，例如 1",
                  "zip": "買受人郵遞區號，例如 407，若沒有則預設 407"
                }
              ],
              "lands": [
                {
                  "section": "地段名稱，例如：順和段",
                  "land_number": "地號，例如：0151-0000",
                  "area": "面積，僅填寫數字（單位為平方公尺），例如：679.07",
                  "holding_numerator": "移轉權利範圍（持分分子），僅數字，例如 1",
                  "holding_denominator": "移轉權利範圍（持分分母），僅數字，例如 1",
                  "value_per_sqm": "公告地段現值，僅填寫數字，例如：4160"
                }
              ],
              "buildings": [
                {
                  "building_number": "建號，例如：183",
                  "door_number": "門牌地址，例如：龍井區三港路水裡港巷68之16號",
                  "land_number": "基地坐落地號，例如：田水段 859-23地號",
                  "area_details": "層次面積明細，例如：一層 43.30, 二層 56.46, 騎樓 15.05",
                  "total_area": "主建物總面積，僅填寫數字，例如：124.7",
                  "attached_area": "附屬建物明細，例如：陽台 2.42",
                  "holding_numerator": "移轉持分分子，僅數字，例如：1",
                  "holding_denominator": "移轉持分分母，僅數字，例如：1",
                  "value_per_sqm": "評定現值，僅填寫數字，若無則填 0",
                  "remarks": "備註，例如：公同共有"
                }
              ]
            }
            
            請不要包含 any Markdown 標記 (如 ```json) 或是其他多餘的說明文字。
            如果某個檔案未提供，或某個欄位在文件中確實找不到，請填寫空字串 ""。
            """
            
            contents.append(prompt)
            
            # 呼叫 Gemini 2.5 Flash
            response_text = self._call_gemini_with_retry(
                client=client,
                model='gemini-2.5-flash',
                contents=contents
            )
            
            return self._parse_response(response_text)
            
        except Exception as e:
            return {"error": f"資料萃取失敗：{str(e)}"}
        finally:
            # 清理雲端暫存檔
            for f in uploaded_files:
                try:
                    client.files.delete(name=f.name)
                except:
                    pass
            # 清理本機 ASCII 暫存檔
            for p in temp_ascii_paths:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except:
                        pass
