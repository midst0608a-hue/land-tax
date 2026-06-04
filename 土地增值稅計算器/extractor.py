import os
import json
import time
from google import genai
from google.genai import types

class GeminiExtractor:
    def __init__(self, api_key: str):
        self.api_key = api_key
        
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
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[file_info, prompt]
                )
            except Exception as e_flash:
                # 不再盲目降級到 1.5-pro，直接回傳真實的錯誤訊息
                return {"error": f"Gemini 2.5 Flash 生成內容時發生錯誤：{str(e_flash)}"}
                
            return self._parse_response(response.text)
            
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
                    config={'mime_type': manual_mime}
                )
                # 等待檔案處理完成
                while True:
                    manual_info = client.files.get(name=uploaded_manual.name)
                    m_state_str = str(manual_info.state)
                    if "ACTIVE" in m_state_str:
                        break
                    elif "FAILED" in m_state_str:
                        return {"error": f"審查手冊檔案處理失敗 (狀態: {m_state_str})"}
                    time.sleep(2)
                contents.append(manual_info)
                
            # 3. 組合 Prompt
            prompt = f"""
            你是一個專業的台灣地政事務所登記課審查人員 (地政登記審查官)。
            請根據使用者提供的案件背景描述，審查上傳的公文/文件影像或 PDF 是否合規。
            
            【案件背景描述】：
            {case_desc}
            
            【你的審查任務】：
            1. 辨識上傳的文件內容 (包含地號、所有權人、統一編號、地址、持分範圍、申報現值、委任代理人資訊、簽章用印欄位、修正塗改痕跡等)。
            2. 如果使用者有另外上傳「審查手冊或指引檔案」，請嚴格依據該指引中的審查規範與要求進行比對。
            3. 如果使用者沒有上傳審查手冊，請使用你所熟知的台灣《土地登記規則》、《土地法》、內政部《土地登記審查手冊》以及常見地政事務所補正駁回規範進行審查。
            
            【重點審查清單】：
            - **文件齊備度**：本案依使用者描述的案情，需要哪些書表與附件？上傳的檔案中是否完整包含？是否有缺漏（如所有權狀、納稅證明、身分證影本、授權書等）？
            - **資訊一致性**：各文件（申請書、公契、契約書、身分證等）上的基本資訊是否完全一致？(例如姓名、統一編號、住所、地建號、面積、持分等)。
            - **用印與簽章**：申請人、代理人或義務人欄位是否有用印或簽名痕跡？是否有修正塗改卻未在旁蓋章認章的情況？
            - **法定切結或備註**：申請書備註欄是否寫入本案法定需要的切結聲明（例如優先購買權切結、法人處分切結、無租賃關係切結、未成年人利益切結等）？
            
            【報告輸出格式】：
            請輸出詳細且結構良好的 Markdown 預審報告，內容包含：
            
            # 📑 土地登記案件預審查報告
            
            ## 📋 案件基本資訊
            - **申辦類型**：(例如：夫妻贈與所有權移轉登記 / 一般買賣所有權移轉)
            - **案情大綱**：(簡述使用者的案件背景)
            
            ## 🔍 核心檢核清單 (檢核項目與結果)
            | 檢核項目 | 結果 | 說明 / 差異發現 |
            | :--- | :--- | :--- |
            | **文件完整性** | ✅ 通過 / ⚠️ 警告 / ❌ 缺失 | (說明是否缺件) |
            | **欄位一致性** | ✅ 通過 / ⚠️ 警告 / ❌ 缺失 | (說明名字、統編、地建號是否相符) |
            | **簽章與塗改** | ✅ 通過 / ⚠️ 警告 / ❌ 缺失 | (說明簽名蓋章或塗改認章情況) |
            | **法定備註與切結** | ✅ 通過 / ⚠️ 警告 / ❌ 缺失 | (說明備註欄切結是否完整) |
            
            ## 💡 審查詳細發現與風險警告
            (請詳細列出哪些地方有錯、不吻合、或有漏章、缺件的風險，以條列式說明)
            
            ## 🛠️ 具體補正與修改建議
            (針對審查發現，教使用者如何修正文件或補齊哪些文件，以避免送件後被地政事務所「通知補正」或「駁回」)
            """
            
            contents.append(prompt)
            
            # 呼叫 Gemini 2.5 Flash
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents
            )
            
            return {"success": True, "report": response.text}
            
        except Exception as e:
            return {"error": f"審查 API 發生錯誤：{str(e)}"}
        finally:
            # 清理檔案
            for item in [uploaded_doc, uploaded_manual]:
                if item:
                    try:
                        client.files.delete(name=item.name)
                    except:
                        pass
            # 清理 ASCII 暫存檔案
            for temp_path in [temp_doc_ascii, temp_manual_ascii]:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass
