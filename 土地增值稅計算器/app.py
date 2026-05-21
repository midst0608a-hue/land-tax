import streamlit as st
import os
import tempfile
from extractor import GeminiExtractor

st.set_page_config(page_title="資料自動萃取神器", page_icon="🤖", layout="wide")

st.title("📄 謄本與身分證自動萃取神器")
st.markdown("""
這個工具可以幫助您從**土地謄本、建物謄本、或身分證件**中，自動萃取出地號、面積、持分、現值、姓名、統編、地址等重要資料。
✅ **支援電子 PDF 檔**
✅ **支援紙本掃描圖檔 (JPG/PNG)**
✅ **支援照片 (例如身分證拍照)**
""")

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
    st.header("⚙️ 設定")
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
    st.markdown("### 💡 如何取得 API Key？")
    st.markdown("1. 前往 [Google AI Studio](https://aistudio.google.com/)")
    st.markdown("2. 登入您的 Google 帳號")
    st.markdown("3. 點擊左側的 **Get API key**")
    st.markdown("4. 建立一組新的金鑰並貼到上方")

# 檢查是否有輸入 API Key
if not st.session_state.api_key:
    st.warning("⚠️ 請先在左側輸入您的 Google Gemini API Key 或是於雲端後台設定 Secrets 才能開始使用！")
    st.stop()

# 檔案上傳區
uploaded_file = st.file_uploader("請上傳謄本或身分證件", type=["pdf", "jpg", "jpeg", "png"])

if uploaded_file is not None:
    # 建立一個暫存資料夾來存放上傳的檔案
    with tempfile.TemporaryDirectory() as temp_dir:
        file_ext = uploaded_file.name.split(".")[-1].lower()
        # 為了避免非英文/特殊字元檔名在不同系統或套件中產生讀取、上傳、編碼或安全性問題（例如 Path Traversal），
        # 我們將暫存檔案統一命名為安全的英文檔名，僅保留原始副檔名
        safe_filename = f"temp_file.{file_ext}"
        file_path = os.path.join(temp_dir, safe_filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        

        
        # 準備執行萃取
        st.info("🤖 AI 正在努力閱讀並萃取資料中，請稍候 (約需 5~15 秒)...")
        
        extractor = GeminiExtractor(api_key=st.session_state.api_key)
        
        with st.spinner("解析中..."):
            if file_ext == "pdf":
                result = extractor.process_pdf(file_path)
            else:
                result = extractor.process_image(file_path)
                
        # 顯示結果
        if "error" in result:
            st.error(f"❌ 發生錯誤：{result['error']}")
            if "raw" in result:
                with st.expander("查看原始 AI 回覆"):
                    st.text(result["raw"])
        else:
            st.success("✅ 萃取成功！")
            
            data_list = result["data"]
            if not isinstance(data_list, list):
                data_list = [data_list] # 確保是陣列
                
            if len(data_list) == 0:
                st.warning("AI 沒有在這份文件中找到相符的資料。")
            else:
                # 組合格式 A 的純文字
                formatted_text = ""
                for i, record in enumerate(data_list):
                    formatted_text += f"【紀錄 {i+1}】\n"
                    # 按照指定的順序排列
                    keys_order = ["地號", "面積", "持分", "現值", "所有權人", "統一編號", "前次移轉現值", "歷次取得範圍", "地址"]
                    
                    # 先排指定的欄位
                    for key in keys_order:
                        if key in record and record[key]:
                            formatted_text += f"{key}：{record[key]}\n"
                            
                    # 再排其他 AI 抓到但不在清單上的欄位 (如果有)
                    for key, value in record.items():
                        if key not in keys_order and value:
                            formatted_text += f"{key}：{value}\n"
                            
                    formatted_text += "\n" # 紀錄之間空一行
                    
                st.markdown("### 📋 萃取結果 (可直接複製)")
                # 使用 st.code 可以產生帶有「複製按鈕」的區塊
                st.code(formatted_text.strip(), language="text")
                
                st.markdown("*(小提示：您可以直接點擊上方文字框右上角的「複製」按鈕)*")
