import streamlit as st
import torch
from transformers import PreTrainedTokenizerFast, BartForConditionalGeneration
import requests
from bs4 import BeautifulSoup
import re

# ==========================================
# 1. 페이지 및 모델 설정
# ==========================================
st.set_page_config(page_title="외교부 소식 요약 봇", page_icon="🤖")

@st.cache_resource
def load_model():
    try:
        # 깃허브 용량 제한 없이 실행되도록 공개된 KoBART 모델 사용
        model_name = "gogamza/kobart-summarization" 
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_name)
        model = BartForConditionalGeneration.from_pretrained(model_name)
        return tokenizer, model
    except Exception as e:
        st.error(f"모델 로딩 중 오류가 발생했습니다: {e}")
        return None, None

tokenizer, model = load_model()

# ==========================================
# 2. [핵심 수정] 강력해진 크롤링 함수 (PostView 방식)
# ==========================================
def get_naver_blog_content(url):
    """
    네이버 블로그 URL에서 blogId와 logNo를 추출하여
    'PostView.naver' (본문 전용 URL)로 직접 접속하는 방식.
    Streamlit Cloud에서의 차단을 우회하기 위함.
    """
    if not url:
        return "에러", "URL 주소가 비어있습니다."

    # 1. 헤더 강화 (봇 차단 회피용)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.naver.com/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }

    try:
        # 2. URL에서 blogId와 logNo 추출 (정규표현식 사용)
        # 예: https://blog.naver.com/mofakr/224099029110
        # blogId = mofakr, logNo = 224099029110
        
        # 모바일 주소면 PC 주소로 1차 변환
        if "m.blog.naver.com" in url:
            url = url.replace("m.blog.naver.com", "blog.naver.com")

        # 정규식으로 아이디와 글번호 찾기
        match = re.search(r'blog\.naver\.com/([a-zA-Z0-9_]+)/([0-9]+)', url)
        
        final_url = url # 기본은 원래 URL
        
        if match:
            blog_id = match.group(1)
            log_no = match.group(2)
            # iframe 없이 본문만 있는 전용 URL 생성
            final_url = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}&redirect=Dlog&widgetTypeCall=true&directAccess=false"
        
        # 3. 요청 보내기
        response = requests.get(final_url, headers=headers)
        
        if response.status_code != 200:
            return "접속 실패", f"서버 응답 코드: {response.status_code}"

        soup = BeautifulSoup(response.text, 'html.parser')

        # 4. 제목 추출
        # PostView 방식에서는 제목 태그가 다를 수 있음
        title_elem = soup.select_one('.se-title-text') or soup.select_one('.htitle') or soup.select_one('h3.se_textarea')
        title = title_elem.text.strip() if title_elem else "제목을 찾을 수 없음"

        # 5. 본문 추출
        # PostView 방식은 #mainFrame(iframe)을 찾을 필요가 없음. 바로 본문 클래스 검색.
        content_elem = soup.select_one('.se-main-container') or soup.select_one('#postViewArea') or soup.select_one('.post_view')

        if content_elem:
            text = content_elem.text
            text = re.sub(r'\n+', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            return title, text.strip()
        else:
            # 디버깅용: 본문을 못 찾았을 때 HTML의 일부를 확인
            return title, None

    except Exception as e:
        return "에러", f"시스템 에러: {e}"

# ==========================================
# 3. RSS 파싱 함수 (강력한 헤더 추가)
# ==========================================
def clean_html(raw_html):
    """CDATA 태그나 HTML 태그 제거용 헬퍼 함수"""
    if not raw_html:
        return ""
    # CDATA 태그 제거
    clean = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', raw_html)
    # HTML 태그 제거 (<p>, <b> 등)
    clean = re.sub(r'<.*?>', '', clean)
    # 특수문자(&nbsp; 등) 제거
    clean = re.sub(r'&[a-z]+;', '', clean)
    return clean.strip()

def get_latest_mofa_news():
    """
    외교부 블로그 RSS를 뒤져서 '소식/보도/대변인' 관련 글만 가져옴
    """
    rss_url = "https://rss.blog.naver.com/mofakr.xml"
    
    # [수정] RSS 요청에도 강력한 헤더 적용 (네이버 차단 회피)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/xml,application/xhtml+xml,text/html;q=0.9, text/plain;q=0.8,image/png,*/*;q=0.5'
    }
    
    try:
        response = requests.get(rss_url, headers=headers)
        
        # 파싱
        try:
            soup = BeautifulSoup(response.content, 'xml')
        except:
            soup = BeautifulSoup(response.content, 'html.parser')
            
        items = soup.find_all('item')
        target_links = []
        
        for item in items:
            category = item.category.text if item.category else ""
            title = item.title.text if item.title else ""
            link = item.link.text if item.link else ""
            
            # CDATA 및 공백 정리
            title = clean_html(title)
            link = link.strip()
            
            if not link:
                continue

            # [필터링 로직]
            if "소식" in category or "보도" in category or "대변인" in category or "외교부" in category:
                target_links.append({"title": title, "link": link})
                if len(target_links) >= 5: 
                    break
        
        # 비상용: 타겟 글 없으면 최신 3개 무조건 가져오기
        if not target_links and items:
            for i in items[:3]:
                t = clean_html(i.title.text)
                l = i.link.text.strip()
                if l:
                    target_links.append({"title": t, "link": l})
            
        return target_links

    except Exception as e:
        # RSS 연결 실패 시 에러 로그는 콘솔에만 찍고 빈 리스트 반환
        print(f"RSS 파싱 에러: {e}")
        return []

# ==========================================
# 4. 요약 함수
# ==========================================
def predict_summary(text):
    if not text or len(text) < 50:
        return "요약할 내용이 너무 짧거나 본문을 가져오지 못했습니다."

    input_ids = tokenizer.encode(text, return_tensors="pt", max_length=1024, truncation=True)

    summary_text_ids = model.generate(
        input_ids=input_ids,
        bos_token_id=model.config.bos_token_id,
        eos_token_id=model.config.eos_token_id,
        length_penalty=1.2,
        max_length=256,
        min_length=30,
        num_beams=4,
        early_stopping=True,
        no_repeat_ngram_size=3
    )
    
    summary = tokenizer.decode(summary_text_ids[0], skip_special_tokens=True)

    if summary and summary[-1] not in ['.', '!', '?']:
        last_punctuation = max(summary.rfind('.'), summary.rfind('!'), summary.rfind('?'))
        if last_punctuation != -1:
            summary = summary[:last_punctuation+1]

    return summary

# ==========================================
# 5. 메인 UI 화면 구성
# ==========================================
st.title("📰 외교부 소식 자동 요약 봇")
st.write("인공지능이 외교부 블로그의 주요 소식을 3줄로 요약해 드립니다.")

if model is None:
    st.error("⚠️ 모델을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
else:
    st.success("AI 모델 준비 완료! (Ready)")

tab1, tab2 = st.tabs(["🔗 URL 직접 입력", "📢 외교부 최신 소식 (자동)"])

# [Tab 1] URL 요약
with tab1:
    st.subheader("뉴스/블로그 주소 입력")
    input_url = st.text_input("요약하고 싶은 네이버 블로그 URL을 입력하세요:")
    
    if st.button("요약 시작", key="btn1"):
        if input_url:
            with st.spinner('크롤링 및 요약 중입니다...'):
                title, raw_text = get_naver_blog_content(input_url)
                
                if raw_text:
                    summary = predict_summary(raw_text)
                    st.markdown(f"### 📄 {title}")
                    st.info(summary)
                    with st.expander("원본 내용 보기"):
                        st.write(raw_text)
                else:
                    st.error("본문을 가져오지 못했습니다. (접근 권한 혹은 삭제된 글)")

# [Tab 2] 외교부 최신 소식
with tab2:
    st.subheader("외교부 주요 소식 (Top 5)")
    st.write("아래 버튼을 누르면 '외교부 소식/보도' 카테고리의 최신 글을 가져옵니다.")
    
    if st.button("최신 소식 가져오기", key="btn2"):
        with st.spinner('외교부 블로그를 스캔하는 중입니다...'):
            news_items = get_latest_mofa_news()
            
            if not news_items:
                st.warning("가져올 소식이 없거나 연결에 실패했습니다.")
            else:
                st.success(f"총 {len(news_items)}개의 최신 소식을 발견했습니다!")
                
                for i, item in enumerate(news_items):
                    st.markdown("---")
                    st.markdown(f"**[{i+1}] {item['title']}**")
                    
                    _, content = get_naver_blog_content(item['link'])
                    
                    if content:
                        summary = predict_summary(content)
                        st.success(summary)
                    else:
                        st.caption("⚠️ 본문 크롤링 실패 (네이버 차단 또는 비공개 글)")
                        st.write(f"링크: {item['link']}")
