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
        7. 出生年月日 (如果是身分證，請抓取出生年月日，例如：「民國60年5月21日」)
        8. 前次移轉現值 (必須包含年月與價格。如果同一個地號有多筆前次移轉紀錄，請分別列出，例如：「109年5月：13,000元／平方公尺；111年2月：15,000元／平方公尺」)
        9. 歷次取得範圍 (若有多筆對應前次移轉的持分取得範圍，也請分別列出)
        10. 地址 (包含身分證上的戶籍地址或謄本上的住址)
        
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
        
        請以嚴格的 JSON 陣列 (JSON Array) 格式回傳，不要包含 any Markdown 標記 (如 ```json) 或是其他多餘的說明文字。
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
                "出生年月日": "民國60年5月21日",
                "前次移轉現值": "109年5月：13,000.0元／平方公尺",
                "歷次取得範圍": "10000分之384",
                "地址": "台中市西屯區協和里..."
            }
        ]
        """

    def process_file(self, file_path: str, mime_type: str):
        uploaded_file = None
        try:
            client = genai.Client(api_key=self.api_key)
            prompt = self._get_prompt()
            
            # 使用 File API 上傳檔案
            uploaded_file = client.files.upload(
                file=file_path, 
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
