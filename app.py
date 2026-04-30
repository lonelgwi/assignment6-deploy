import streamlit as st
import requests
import time
import json
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
# 팁: 배포 시에는 st.secrets["GEMINI_API_KEY"] 방식을 사용하는 것이 보안상 안전합니다.
API_KEY = "" 
MODEL_ID = "gemini-2.5-flash-preview-09-2025"

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
    .stTextArea>div>div>textarea { border-radius: 12px; border: 1px solid #ddd; }
    .summary-box { 
        background-color: #ffffff; 
        padding: 24px; 
        border-radius: 16px; 
        border-left: 6px solid #1a73e8; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        margin: 15px 0;
        line-height: 1.6;
    }
    .news-card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #eee;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# [1] AI 엔진 함수 (Gemini API)
# ==========================================
def call_gemini_api(prompt, system_instruction):
    """
    Gemini API를 호출하여 텍스트를 생성합니다.
    실패 시 지수 백오프 전략을 사용하여 재시도합니다.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]}
    }
    
    headers = {"Content-Type": "application/json"}
    
    for i in range(6):  # 최대 5회 재시도
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text']
            elif response.status_code == 429: # 할당량 초과 시 대기
                time.sleep(2 ** i)
            else:
                break
        except Exception:
            time.sleep(2 ** i)
            
    return "현재 요약 엔진을 사용할 수 없습니다. 잠시 후 다시 시도해주세요."

def summarize_text(text):
    """입력된 텍스트를 외교 전문 스타일로 요약"""
    if len(text.strip()) < 20:
        return "요약할 내용이 너무 충분하지 않습니다. 조금 더 긴 내용을 입력해주세요."
    
    system_prompt = (
        "당신은 외교부 소식을 전달하는 전문 큐레이터입니다. "
        "입력된 보도자료나 기사를 분석하여 핵심 내용을 3개의 불렛 포인트로 요약하세요. "
        "문장은 '~했습니다'와 같이 정중한 공문서체로 작성하고, 전문 용어는 문맥에 맞게 쉽게 풀어서 설명하세요."
    )
    return call_gemini_api(text, system_prompt)

# ==========================================
# [2] 데이터 수집 함수 (RSS & Scraping)
# ==========================================
@st.cache_data(ttl=3600) # 1시간 동안 결과 캐싱
def get_mofa_news_list():
    """외교부 네이버 블로그 RSS에서 최신 소식 목록 추출"""
    try:
        rss_url = "https://rss.blog.naver.com/mofakr.xml"
        res = requests.get(rss_url, timeout=10)
        soup = BeautifulSoup(res.content, "xml")
        items = soup.find_all("item")
        
        valid_news = []
        for item in items:
            category = item.category.text if item.category else ""
            # 관련 카테고리 필터링
            if any(kw in category for kw in ["소식", "보도", "대변인", "브리핑"]):
                valid_news.append({
                    "title": item.title.text,
                    "link": item.link.text,
                    "pubDate": item.pubDate.text if item.pubDate else ""
                })
                if len(valid_news) >= 5: break # 최신 5개만 가져옴
        return valid_news
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return []

def get_full_content(url):
    """네이버 블로그 URL에서 실제 본문 텍스트 추출"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        # 모바일 링크 처리
        url = url.replace("m.blog", "blog")
        
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 네이버 블로그는 본문이 iframe 안에 있음
        iframe = soup.select_one("iframe#mainFrame")
        if iframe:
            inner_url = "https://blog.naver.com" + iframe["src"]
            res = requests.get(inner_url, headers=headers)
            soup = BeautifulSoup(res.text, "html.parser")
            
        # 다양한 본문 선택자 대응
        content_area = soup.select_one(".se-main-container") or soup.select_one("#postViewArea")
        if content_area:
            # 불필요한 공백 및 개행 정리
            text = content_area.get_text(separator=' ')
            return ' '.join(text.split())
        return None
    except Exception:
        return None

# ==========================================
# [3] 메인 UI 구성
# ==========================================
def main():
    st.title("📢 외교부 소식 자동 요약 봇 v2.1")
    st.info("최신 외교 동향과 보도자료를 AI가 분석하여 핵심만 요약해 드립니다.")

    tab1, tab2 = st.tabs(["✍️ 직접 입력 요약", "📰 최신 외교부 피드"])

    # --- 탭 1: 직접 입력 ---
    with tab1:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("원문 입력")
            input_txt = st.text_area(
                "요약이 필요한 텍스트를 입력하세요.", 
                placeholder="여기에 보도자료나 기사 본문을 붙여넣으세요...",
                height=400
            )
            submit_btn = st.button("핵심 요약하기", key="btn_manual")
        
        with col2:
            st.subheader("AI 분석 결과")
            if submit_btn:
                if input_txt:
                    with st.spinner("전문 AI가 문맥을 분석하고 있습니다..."):
                        summary = summarize_text(input_txt)
                        st.markdown(f'<div class="summary-box">{summary}</div>', unsafe_allow_html=True)
                else:
                    st.warning("텍스트를 먼저 입력해주세요.")

    # --- 탭 2: 자동 수집 피드 ---
    with tab2:
        st.subheader("외교부 공식 블로그 최신 소식 (실시간)")
        
        if st.button("🔄 소식 새로고침", key="btn_refresh"):
            st.cache_data.clear() # 캐시 강제 삭제

        news_items = get_mofa_news_list()
        
        if not news_items:
            st.write("가져올 수 있는 최신 소식이 없습니다.")
        else:
            for idx, item in enumerate(news_items):
                with st.container():
                    st.markdown(f"#### {item['title']}")
                    st.caption(f"📅 {item['pubDate']} | [원문 읽기]({item['link']})")
                    
                    # 요약 버튼을 각 뉴스별로 배치
                    if st.button(f"이 소식 요약하기", key=f"btn_news_{idx}"):
                        with st.spinner("본문을 수집하여 요약 중입니다..."):
                            full_text = get_full_content(item['link'])
                            if full_text:
                                summary = summarize_text(full_text)
                                st.markdown(f'<div class="summary-box"><b>AI 핵심 요약:</b><br><br>{summary}</div>', unsafe_allow_html=True)
                                with st.expander("본문 미리보기"):
                                    st.write(full_text[:1000] + "...")
                            else:
                                st.error("본문 내용을 가져오는 데 실패했습니다.")
                    st.divider()

    # Footer
    st.sidebar.markdown("### 서비스 정보")
    st.sidebar.write("이 서비스는 외교부 보도자료를 효율적으로 파악하기 위해 제작된 AI 도우미입니다.")
    st.sidebar.divider()
    st.sidebar.caption("v2.1 Update: Gemini-2.5-Flash Engine Applied")

if __name__ == "__main__":
    main()
