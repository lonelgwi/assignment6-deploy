import streamlit as st
import requests
import time
import json
import os
from bs4 import BeautifulSoup

# ==========================================
# [설정] 페이지 설정 및 스타일
# ==========================================
st.set_page_config(
    page_title="외교부 소식 요약", 
    page_icon="📢", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# API 설정
# 배포 환경에서는 Streamlit Cloud의 Settings > Secrets에 GEMINI_API_KEY를 등록하세요.
API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

# 모델 ID와 API 버전 설정
MODEL_ID = "gemini-flash-latest"
API_VERSION = "v1beta" 

# UI 스타일 커스터마이징
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { 
        width: 100%; 
        border-radius: 12px; 
        height: 3.5em; 
        background-color: #1a73e8; 
        color: white; 
        font-weight: bold;
        border: none;
        transition: 0.3s;
    }
    .stButton>button:hover { background-color: #1557b0; border: none; }
    .summary-box { 
        background-color: #ffffff; 
        padding: 24px; 
        border-radius: 16px; 
        border-left: 6px solid #1a73e8; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        margin: 15px 0;
        line-height: 1.6;
        color: #1e293b;
    }
    .content-box {
        background-color: #f1f5f9;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        margin-top: 10px;
        font-size: 0.95em;
        line-height: 1.7;
        color: #334155;
        white-space: pre-wrap;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# [1] AI 엔진 함수 (Gemini API)
# ==========================================
def call_gemini_api(prompt, system_instruction):
    if not API_KEY:
        return "⚠️ API 키가 설정되지 않았습니다. Streamlit Secrets에서 GEMINI_API_KEY를 등록해주세요."

    url = f"https://generativelanguage.googleapis.com/{API_VERSION}/models/{MODEL_ID}:generateContent"
    
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": API_KEY
    }
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"System Instruction: {system_instruction}\n\nUser Input: {prompt}"
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
        }
    }
    
    for i in range(3):
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and len(result['candidates']) > 0:
                    return result['candidates'][0]['content']['parts'][0]['text']
                return "AI가 응답을 생성했지만 내용을 추출할 수 없습니다."
            
            elif response.status_code == 404:
                return f"❌ 404 오류: 모델 경로를 찾을 수 없습니다. (모델: {MODEL_ID}, 버전: {API_VERSION})"
            
            elif response.status_code == 403:
                return "❌ 403 오류: API 키 권한이 없거나 차단되었습니다."
            
            elif response.status_code == 429:
                time.sleep(2 ** i)
            else:
                return f"에러 발생 (코드: {response.status_code})\n{response.text}"
        except Exception as e:
            if i == 2: return f"연결 오류 발생: {str(e)}"
            time.sleep(1)
            
    return "요약 서비스 연결에 실패했습니다."

def summarize_text(text):
    if not text or len(text.strip()) < 20:
        return "내용이 너무 짧아 요약할 수 없습니다. (최소 20자 이상)"
    
    system_prompt = "당신은 외교부 소식 요약 전문가입니다. 입력된 텍스트의 핵심 내용을 3가지 불렛포인트로 요약하세요. 정중한 한국어(~했습니다 체)를 사용하세요."
    return call_gemini_api(text, system_prompt)

# ==========================================
# [2] 데이터 수집 함수
# ==========================================
@st.cache_data(ttl=3600)
def get_mofa_news_list():
    try:
        rss_url = "https://rss.blog.naver.com/mofakr.xml"
        res = requests.get(rss_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        items = soup.find_all("item")
        
        valid_news = []
        for item in items:
            category = item.category.text if item.category else ""
            if any(kw in category for kw in ["소식", "보도", "대변인", "브리핑"]):
                valid_news.append({
                    "title": item.title.text,
                    "link": item.link.text,
                    "pubDate": item.pubDate.text if item.pubDate else ""
                })
                if len(valid_news) >= 5: break
        return valid_news
    except:
        return []

def get_full_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = url.replace("m.blog", "blog")
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        iframe = soup.select_one("iframe#mainFrame")
        if iframe:
            res = requests.get("https://blog.naver.com" + iframe["src"], headers=headers)
            soup = BeautifulSoup(res.text, "html.parser")
        content_area = soup.select_one(".se-main-container") or soup.select_one("#postViewArea")
        return ' '.join(content_area.get_text(separator=' ').split()) if content_area else None
    except:
        return None

# ==========================================
# [3] 메인 UI 구성
# ==========================================
def main():
    st.title("📢 외교부 소식 자동 요약 봇")
    st.info("최신 외교 동향을 AI를 통해 빠르게 파악하고 전문을 확인하세요.")
    
    # 세션 상태에 요약과 전문을 함께 저장하도록 구조 변경
    if 'news_data' not in st.session_state:
        st.session_state.news_data = {}

    tab1, tab2 = st.tabs(["✍️ 직접 입력 요약", "📰 최신 소식 리스트"])

    with tab1:
        input_txt = st.text_area("요약할 본문을 붙여넣으세요.", height=300)
        if st.button("AI 요약 시작", key="btn_man"):
            if input_txt:
                with st.spinner("AI 분석 중..."):
                    summary = summarize_text(input_txt)
                    st.markdown("### ✨ AI 요약 결과")
                    st.markdown(f'<div class="summary-box">{summary}</div>', unsafe_allow_html=True)
            else:
                st.warning("내용을 입력해주세요.")

    with tab2:
        news_items = get_mofa_news_list()
        if not news_items:
            st.write("소식을 불러올 수 없습니다.")
        else:
            for idx, item in enumerate(news_items):
                st.markdown(f"### {item['title']}")
                st.caption(f"📅 발행일: {item['pubDate']}")
                
                if st.button(f"요약 및 전문 보기", key=f"btn_{idx}"):
                    with st.spinner("본문을 수집하고 요약하는 중..."):
                        content = get_full_content(item['link'])
                        if content:
                            summary = summarize_text(content)
                            # 요약과 전문을 함께 저장
                            st.session_state.news_data[item['link']] = {
                                "summary": summary,
                                "full_text": content
                            }
                        else:
                            st.error("본문을 가져오는 데 실패했습니다.")
                
                # 데이터가 존재하면 출력
                if item['link'] in st.session_state.news_data:
                    data = st.session_state.news_data[item['link']]
                    
                    st.markdown("#### 🤖 AI 핵심 요약")
                    st.markdown(f'<div class="summary-box">{data["summary"]}</div>', unsafe_allow_html=True)
                    
                    # 전문 보기 섹션 (Expander 사용)
                    with st.expander("📄 기사 전문 읽기", expanded=False):
                        st.markdown(f'<div class="content-box">{data["full_text"]}</div>', unsafe_allow_html=True)
                        st.caption(f"[원문 링크로 이동하기]({item['link']})")
                
                st.divider()

if __name__ == "__main__":
    main()
