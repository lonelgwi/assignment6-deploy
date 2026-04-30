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
    page_title="외교부 소식 요약 봇", 
    page_icon="📢", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# API 설정
# 팁: 배포 환경에서는 st.secrets["GEMINI_API_KEY"]를 사용하여 키를 관리하세요.
API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

# 모델 ID를 가장 범용적인 gemini-1.5-flash로 변경 (403 오류 방지)
MODEL_ID = "gemini-1.5-flash" 

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
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# [1] AI 엔진 함수 (Gemini API)
# ==========================================
def call_gemini_api(prompt, system_instruction):
    if not API_KEY:
        return "⚠️ API 키가 설정되지 않았습니다. Streamlit Secrets에서 GEMINI_API_KEY를 등록해주세요."

    # API URL 구성
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]}
    }
    
    headers = {"Content-Type": "application/json"}
    
    for i in range(3):  # 재시도 횟수 조정
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result:
                    return result['candidates'][0]['content']['parts'][0]['text']
                return "응답 데이터를 해석할 수 없습니다."
            elif response.status_code == 403:
                return "❌ API 권한 오류(403): API 키가 이 모델({0})을 지원하지 않거나 활성화되지 않았습니다.".format(MODEL_ID)
            elif response.status_code == 429:
                time.sleep(2 ** i)
            else:
                return f"에러 발생 (코드: {response.status_code})"
        except Exception as e:
            time.sleep(1)
            
    return "요약 서비스 연결에 실패했습니다."

def summarize_text(text):
    if not text or len(text.strip()) < 20:
        return "요약할 내용이 너무 짧습니다."
    
    system_prompt = "당신은 외교부 소식 요약 전문가입니다. 핵심 내용을 3가지 불렛포인트로 요약하세요."
    return call_gemini_api(text, system_prompt)

# ==========================================
# [2] 데이터 수집 함수 (기존 유지)
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
# [3] 메인 UI
# ==========================================
def main():
    st.title("📢 외교부 소식 자동 요약 봇")
    
    if 'news_summaries' not in st.session_state:
        st.session_state.news_summaries = {}

    tab1, tab2 = st.tabs(["✍️ 직접 입력", "📰 최신 소식 피드"])

    with tab1:
        input_txt = st.text_area("내용을 입력하세요.", height=300)
        if st.button("AI 요약", key="btn_man"):
            if input_txt:
                with st.spinner("분석 중..."):
                    st.markdown(f'<div class="summary-box">{summarize_text(input_txt)}</div>', unsafe_allow_html=True)

    with tab2:
        news_items = get_mofa_news_list()
        for idx, item in enumerate(news_items):
            st.markdown(f"#### {item['title']}")
            if st.button(f"요약 보기", key=f"btn_{idx}"):
                with st.spinner("진행 중..."):
                    content = get_full_content(item['link'])
                    if content:
                        summary = summarize_text(content)
                        st.session_state.news_summaries[item['link']] = summary
            
            if item['link'] in st.session_state.news_summaries:
                st.markdown(f'<div class="summary-box">{st.session_state.news_summaries[item["link"]]}</div>', unsafe_allow_html=True)
            st.divider()

if __name__ == "__main__":
    main()
