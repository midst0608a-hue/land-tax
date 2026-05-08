import os
import time
import json
import google.generativeai as genai
from PIL import Image

class GeminiExtractor:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        # 退回穩定版 SDK，但使用 Pro 最新模型來避開 404 與套件衝突
        self.model = genai.GenerativeModel('gemini-1.5-pro-latest')
        
    def _get_prompt(self):
        return """
        你是一個專業的台灣不動產與身分證件資料萃取助理。
        請分析使用者提供的文件 (可能是土地謄本、建物謄本，或是身分證件)。
        
        請從文件中萃取以下所有欄位：
        1. 地號 (如果是土地謄本)
        2. 面積 (包含單位，如平方公尺)
        3. 持分 (權利範圍)
        4. 現值 (當期申報地價或前次移轉現值)
        5. 所有權人 (姓名)
        6. 統一編號 (身分證字號或統編)
        7. 前次移轉現值
        8. 歷次取得範圍
        9. 地址 (包含身分證上的戶籍地址或謄本上的住址)
        
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
                "前次移轉現值": "13,000.0元／平方公尺",
                "歷次取得範圍": "10000分之384",
                "地址": "台中市西屯區協和里..."
            }
        ]
        """

    def process_image(self, image_path: str):
        """處理單張圖片 (如身分證 JPG/PNG)"""
        try:
            img = Image.open(image_path)
            response = self.model.generate_content([self._get_prompt(), img])
            return self._parse_response(response.text)
        except Exception as e:
            return {"error": str(e)}

    def process_pdf(self, pdf_path: str):
        """處理 PDF 檔案 (如電子謄本或掃描謄本)"""
        try:
            # 上傳 PDF 到 Gemini API
            uploaded_file = genai.upload_file(path=pdf_path, display_name="Document")
            
            # 等待檔案處理完畢
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = genai.get_file(uploaded_file.name)
                
            if uploaded_file.state.name == "FAILED":
                return {"error": "PDF 處理失敗，請確認檔案格式是否正確。"}

            response = self.model.generate_content([self._get_prompt(), uploaded_file])
            
            # 處理完畢後刪除檔案，保護隱私
            genai.delete_file(uploaded_file.name)
            
            return self._parse_response(response.text)
        except Exception as e:
            return {"error": str(e)}

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
