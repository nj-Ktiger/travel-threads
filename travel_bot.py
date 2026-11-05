import os
import random
import re
import sys
import time
import requests
from google import genai
from google.genai.errors import APIError

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

HISTORY_FILE = "history_topics.txt"

# 감성 넘치는 고화질 랜드마크 사진 큐레이션 (1080px 최적화)
CURATED_PHOTOS = {
    "paris": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=1080&q=80",
    "swiss": "https://images.unsplash.com/photo-1530122037265-a5f1f91d3b99?w=1080&q=80",
    "rome": "https://images.unsplash.com/photo-1529260830199-42c24126f198?w=1080&q=80",
    "london": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=1080&q=80",
    "spain": "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=1080&q=80",
    "tokyo": "https://images.unsplash.com/photo-1503899036084-c55cdd92da26?w=1080&q=80",
    "kyoto": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=1080&q=80",
    "sapporo": "https://images.unsplash.com/photo-1542051841857-5f90071e7989?w=1080&q=80",
    "bali": "https://images.unsplash.com/photo-1537996194471-e657df975ab4?w=1080&q=80",
    "bangkok": "https://images.unsplash.com/photo-1508009603885-50cf7c579365?w=1080&q=80",
    "danang": "https://images.unsplash.com/photo-1559592413-7cec4d0cae2b?w=1080&q=80",
    "jeju": "https://images.unsplash.com/photo-1548115184-bc6544d06a58?w=1080&q=80",
    "flight": "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?w=1080&q=80",
    "europe": "https://images.unsplash.com/photo-1467269204594-9661b134dd2b?w=1080&q=80",
}

# 요즘 쓰레드에서 저장/공유 폭발하는 핵심 카테고리 풀
VIRAL_TRAVEL_CATEGORIES = [
    {"region": "유럽 (파리/런던/스위스/이탈리아/스페인)", "type": "현지인만 아는 실전 압축 꿀팁 3줄 요약", "tag": "europe"},
    {"region": "일본 (도쿄/오사카/교토/후쿠오카/삿포로)", "type": "처음 가면 100% 멘붕 오는 동선/교통/환전 3줄 요약", "tag": "japan"},
    {"region": "동남아 (발리/다낭/방콕/푸꾸옥)", "type": "가성비 럭셔리 휴양지 실패 없는 꿀팁 3줄 요약", "tag": "southeast_asia"},
    {"region": "공항/항공권/짐싸기", "type": "여행 고수들만 써먹는 비행기/공항 꿀팁 3줄 요약", "tag": "flight"},
    {"region": "국내 감성 여행 (제주/강릉/경주/남해)", "type": "한국인도 잘 모르는 인생샷 명소 3줄 요약", "tag": "korea"},
]


def load_history() -> list[str]:
    """최근 다룬 주제 목록을 불러옵니다."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def save_history(topic: str) -> None:
    """새로 다룬 주제를 기록합니다."""
    history = load_history()
    history.append(topic)
    history = history[-100:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write("# 다룬 여행 주제 목록 (중복 방지)\n")
        for t in history:
            f.write(f"{t}\n")


def match_photo_url(keyword: str) -> str:
    """키워드에 가장 어울리는 고화질 랜드마크 사진을 반환합니다."""
    kw = keyword.lower()
    if any(k in kw for k in ["paris", "france", "파리", "프랑스", "에펠탑"]):
        return CURATED_PHOTOS["paris"]
    if any(k in kw for k in ["swiss", "alps", "스위스", "알프스", "융프라우", "인터라켄"]):
        return CURATED_PHOTOS["swiss"]
    if any(k in kw for k in ["rome", "italy", "venice", "로마", "이탈리아", "베니스"]):
        return CURATED_PHOTOS["rome"]
    if any(k in kw for k in ["london", "uk", "런던", "영국"]):
        return CURATED_PHOTOS["london"]
    if any(k in kw for k in ["spain", "barcelona", "스페인", "바르셀로나"]):
        return CURATED_PHOTOS["spain"]
    if any(k in kw for k in ["tokyo", "도쿄", "시부야", "신주쿠"]):
        return CURATED_PHOTOS["tokyo"]
    if any(k in kw for k in ["kyoto", "osaka", "교토", "오사카", "후쿠오카", "일본"]):
        return CURATED_PHOTOS["kyoto"]
    if any(k in kw for k in ["sapporo", "hokkaido", "삿포로", "홋카이도", "눈꽃"]):
        return CURATED_PHOTOS["sapporo"]
    if any(k in kw for k in ["bali", "발리"]):
        return CURATED_PHOTOS["bali"]
    if any(k in kw for k in ["bangkok", "thailand", "방콕", "태국"]):
        return CURATED_PHOTOS["bangkok"]
    if any(k in kw for k in ["danang", "vietnam", "phu quoc", "다낭", "베트남", "푸꾸옥"]):
        return CURATED_PHOTOS["danang"]
    if any(k in kw for k in ["jeju", "korea", "제주", "강릉", "국내", "남해"]):
        return CURATED_PHOTOS["jeju"]
    if any(k in kw for k in ["flight", "airport", "비행기", "공항", "항공", "짐싸기"]):
        return CURATED_PHOTOS["flight"]

    return CURATED_PHOTOS["europe"]


def generate_with_gemini(client: genai.Client, prompt: str) -> str:
    """Gemini 모델 호출 (안정적인 fallback 탑재)"""
    models_to_try = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash"]
    last_error = None
    for model_name in models_to_try:
        try:
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res.text and res.text.strip():
                return res.text.strip()
        except APIError as e:
            print(f"[알림] {model_name} 호출 에러: {e}. 다음 모델 시도...")
            last_error = e
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Gemini API 호출에 모두 실패했습니다: {last_error}")


def create_viral_travel_content() -> dict:
    """
    쓰레드에서 저장/좋아요가 폭발하는 '3줄 요약' 압축형 정보성 콘텐츠를 생성합니다.
    (블로그 홍보/링크 멘트 일체 배제, 순수 100% 바이럴 꿀팁)
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    history = load_history()

    category = random.choice(VIRAL_TRAVEL_CATEGORIES)
    recent_summary = "\n".join([f"- {h}" for h in history[-8:]])

    prompt = f"""
당신은 인스타그램 쓰레드(Threads)에서 2030 여행 꿀팁으로 수만 저장/좋아요를 받는 인기 여행 인플루언서입니다.
오늘 다룰 메인 테마: [{category['region']} - {category['type']}]

[최근 다룬 주제들 - 중복 피할 것]
{recent_summary}

요즘 쓰레드에서 가장 반응이 뜨거운 트렌드는 **"사족 없는 3줄 요약 + 실전 알짜 꿀팁"**입니다.
피드를 내리던 사용자가 무조건 [저장]을 누르고 친구를 태그할 수밖에 없도록,
가독성이 압도적이고 군더더기 없는 완결형 정보 글을 작성하세요.

[절대 금지 규칙 - 엄격 준수]
- ❌ "블로그 방문하세요", "프로필 링크 확인", "블로그에 정리해 둠" 등 블로그/홍보 관련 단어 일체 언급 금지! (순수한 100% 정보 글이어야 사람들이 '저장'을 누르고 프로필을 알아서 찾아봅니다.)
- ❌ 길고 지루한 일기나 감성 미사여구 금지.

[필수 작성 규칙]
1. 첫 문장 후킹: 직관적이고 시선을 끄는 제목형 첫 줄
   - 예시: "유럽 여행 갈 때 모르면 100만원 손해보는 꿀팁 3줄 요약 🇪🇺"
   - 예시: "파리 지하철 소매치기 100% 피하는 법 3줄 요약 🇫🇷"
   - 예시: "스위스 융프라우 갈 때 한국인 90%가 놓치는 꿀팁 3줄 요약 🇨🇭"
2. 📌 3줄 요약:
   1. (구체적 지명/방법과 실전 꿀팁 1)
   2. (구체적 지명/방법과 실전 꿀팁 2)
   3. (구체적 지명/방법과 실전 꿀팁 3)
3. 💡 한 줄 꿀팁: 현지에서 진짜 유용한 팁 1개 추가
4. 저장 유도: "📌 이번 여행 가실 때 꼭 써먹게 미리 [저장]해 두세요!"
5. 인기 해시태그 3~4개

[출력 형식 - 아래 구분자를 정확히 지켜주세요]
TOPIC_TITLE: [오늘의 핵심 주제 (예: 스위스 융프라우 알짜 꿀팁 3줄 요약)]
PHOTO_SEARCH: [위 내용과 직결된 영문 도시/명소 키워드 (예: Swiss Alps, Paris, Rome, Kyoto, London, Bali)]
---THREADS_POST_START---
[여기에 쓰레드에 바로 복사해서 올릴 본문 텍스트 전체를 작성하세요]
---THREADS_POST_END---
"""

    res_text = generate_with_gemini(client, prompt)

    topic_title = "오늘의 여행 꿀팁 3줄 요약"
    photo_search = "Europe"
    threads_post = ""

    t_match = re.search(r"TOPIC_TITLE:\s*(.+)", res_text)
    if t_match:
        topic_title = t_match.group(1).strip()

    p_match = re.search(r"PHOTO_SEARCH:\s*(.+)", res_text)
    if p_match:
        photo_search = p_match.group(1).strip().strip("[]").strip('"')

    c_match = re.search(
        r"---THREADS_POST_START---([\s\S]*?)---THREADS_POST_END---", res_text
    )
    if c_match:
        threads_post = c_match.group(1).strip()
    else:
        threads_post = re.sub(
            r"^(TOPIC_TITLE|PHOTO_SEARCH):.*$", "", res_text, flags=re.MULTILINE
        ).strip()

    photo_url = match_photo_url(f"{photo_search} {topic_title}")

    return {
        "topic": topic_title,
        "photo_search": photo_search,
        "photo_url": photo_url,
        "threads_post": threads_post,
    }


def send_to_telegram(data: dict) -> None:
    """스마트폰 텔레그램으로 고화질 사진과 복사용 텍스트를 전송합니다."""
    # 1. 고화질 사진 전송 (sendPhoto)
    photo_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    caption_intro = (
        f"📸 [오늘의 쓰레드 추천 랜드마크 사진]\n"
        f"🏷️ 주제: {data['topic']}\n\n"
        f"💡 위 사진 꾹 눌러 갤러리에 저장하고,\n"
        f"아래 글을 꾹 눌러 복사 ➔ 쓰레드에 바로 올리세요! (3초 컷)"
    )

    photo_payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": data["photo_url"],
        "caption": caption_intro,
    }

    try:
        p_resp = requests.post(photo_api, json=photo_payload, timeout=15)
        if not p_resp.ok:
            print(f"[경고] 사진 전송 실패 ({p_resp.status_code}): {p_resp.text}")
    except Exception as e:
        print(f"[경고] 사진 전송 오류: {e}")

    # 2. 폰에서 터치 한 번으로 깔끔하게 복사할 수 있도록 본문만 단독 전송 (sendMessage)
    msg_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    msg_payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": data["threads_post"],
        "disable_web_page_preview": True,
    }

    m_resp = requests.post(msg_api, json=msg_payload, timeout=15)
    if not m_resp.ok:
        print(f"[에러] 텍스트 전송 실패: {m_resp.status_code} - {m_resp.text}")
        m_resp.raise_for_status()


def validate_env() -> None:
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        print(f"[에러] 필수 환경변수 누락: {', '.join(missing)}")
        sys.exit(1)


def main():
    validate_env()
    print("1. 쓰레드 대세 트렌드 '3줄 요약' 순수 정보형 콘텐츠 생성 중...")
    data = create_viral_travel_content()
    print(f"   -> 주제: {data['topic']}")
    print(f"   -> 사진 매칭: {data['photo_search']}")
    print(f"   -> 사진 URL: {data['photo_url']}")

    print("2. 텔레그램으로 고화질 사진 및 복사용 텍스트 전송 중...")
    send_to_telegram(data)

    print("3. 이력 저장 중...")
    save_history(data["topic"])
    print("완료! 스마트폰 텔레그램 봇 채팅방을 확인하세요.")


if __name__ == "__main__":
    main()
