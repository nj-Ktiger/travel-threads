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

# 감성 넘치는 고화질 랜드마크/여행 사진 큐레이션 (1080px)
CURATED_PHOTOS = {
    "paris": "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=1080&q=80",
    "swiss": "https://images.unsplash.com/photo-1530122037265-a5f1f91d3b99?w=1080&q=80",
    "rome": "https://images.unsplash.com/photo-1529260830199-42c24126f198?w=1080&q=80",
    "london": "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=1080&q=80",
    "spain": "https://images.unsplash.com/photo-1583422409516-2895a77efded?w=1080&q=80",
    "tokyo": "https://images.unsplash.com/photo-1503899036084-c55cdd92da26?w=1080&q=80",
    "kyoto": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=1080&q=80",
    "osaka": "https://images.unsplash.com/photo-1590559899731-a382839e5549?w=1080&q=80",
    "sapporo": "https://images.unsplash.com/photo-1542051841857-5f90071e7989?w=1080&q=80",
    "bali": "https://images.unsplash.com/photo-1537996194471-e657df975ab4?w=1080&q=80",
    "bangkok": "https://images.unsplash.com/photo-1508009603885-50cf7c579365?w=1080&q=80",
    "danang": "https://images.unsplash.com/photo-1559592413-7cec4d0cae2b?w=1080&q=80",
    "jeju": "https://images.unsplash.com/photo-1548115184-bc6544d06a58?w=1080&q=80",
    "flight": "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?w=1080&q=80",
    "airport": "https://images.unsplash.com/photo-1530521954074-e64f6810b32d?w=1080&q=80",
    "europe": "https://images.unsplash.com/photo-1467269204594-9661b134dd2b?w=1080&q=80",
}

# 쓰레드에서 댓글 수백 개 터지는 4대 논쟁 테마
DEBATE_THEMES = [
    {
        "type": "호불호 극단 논쟁",
        "desc": "낭만 원탑 vs 환상 와장창 깨짐 (파리 소매치기/악취 vs 낭만, 발리 생각보다 덥고 트래픽 vs 천국, 런던 음식 최악 vs 인생도시 등)",
    },
    {
        "type": "경험자 소환형 참견 유도",
        "desc": "가본 사람들만 아는 '남들 다 사는데 솔직히 돈 아까운 것' (돈키호테 거품템, 다낭 쇼핑리스트 함정, 유럽 갈 때 괜히 챙겨서 짐만 된 것 등)",
    },
    {
        "type": "돈값 한다 vs 돈 낭비다 (가격/가성비 논쟁)",
        "desc": "스위스 융프라우 왕복 25만원 티켓 무조건 필수다 vs 그냥 인터라켄 호수 산책이 낫다, 비즈니스석 살 돈으로 5성급 호텔 업그레이드 vs 비행기 피로 줄이기 등",
    },
    {
        "type": "여행 갈 때 사람 미치게 만드는 밸런스 게임",
        "desc": "분 단위 엑셀 계획 J친구 vs 비행기 타기 직전까지 몸만 오는 무계획 P친구, 비행기 이코노미석 등받이 젖히기 내 권리다 vs 뒷사람 민폐다 등",
    },
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
    if any(k in kw for k in ["osaka", "오사카", "도톤보리"]):
        return CURATED_PHOTOS["osaka"]
    if any(k in kw for k in ["tokyo", "도쿄", "시부야", "신주쿠"]):
        return CURATED_PHOTOS["tokyo"]
    if any(k in kw for k in ["kyoto", "교토", "후쿠오카", "일본", "돈키호테"]):
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
    if any(k in kw for k in ["flight", "airport", "비행기", "공항", "항공", "등받이", "여권"]):
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


def create_debate_travel_content() -> dict:
    """
    쓰레드에서 댓글/토론이 폭발하는 논쟁/밸런스형 여행 피드 글을 생성합니다.
    (직접 안 가봤어도 자연스럽게 질문을 던져 댓글을 유도하는 포맷)
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    history = load_history()

    theme = random.choice(DEBATE_THEMES)
    recent_summary = "\n".join([f"- {h}" for h in history[-8:]])

    prompt = f"""
당신은 인스타그램 쓰레드(Threads)에서 댓글 수백 개를 폭발시키는 감각적인 여행 크리에이터입니다.
오늘 다룰 논쟁 테마: [{theme['type']} - {theme['desc']}]

[최근 다룬 주제들 - 중복 피할 것]
{recent_summary}

[쓰레드 댓글 폭발 핵심 공식]
1. 화자의 입장: "내가 전문가인 척" 가르치는 게 아니라, **"주변에서/인터넷에서 의견이 극단으로 갈려서 너무 궁금한 사람"** 또는 **"질문을 던지며 판을 깔아주는 사람"** 포지션입니다. (직접 안 가봤어도 100% 자연스러움)
2. 첫 문장 후킹: 보자마자 손가락을 멈추게 만드는 도발적이거나 공감되는 한 줄 질문
   - 예: "솔직히 파리 여행… 낭만 원탑이다 vs 소매치기에 냄새나서 환상 다 깨진다?"
   - 예: "일본 n번째 다녀오신 분들께 진지하게 묻습니다. 돈키호테에서 솔직히 이건 거품이다 하는 거 1위가 뭔가요?"
   - 예: "스위스 융프라우 왕복 25만원 기차표… 무조건 돈값 한다 vs 그냥 인터라켄 호수가 낫다?"
   - 예: "비행기 이코노미석 등받이 끝까지 젖히는 거… 내 권리다 vs 뒤 사람 민폐다?"
3. 본문 구성:
   - 양측의 입장을 아주 그럴듯하게 2가지로 요약 (사람들이 읽고 '어? 내 얘기네' 하게 만들기)
   - 마지막 줄: 다녀온 사람들의 참견 본능을 자극하는 강력한 질문 ("가보신 분들 솔직히 어떠셨어요?", "여러분의 선택은?")
4. 글자 수: 쓰레드 1개 화면에 딱 들어오는 250~350자 내외 (절대 길게 쓰지 말 것)
5. ❌ 금지 규칙: 블로그 방문, 링크, 광고성 멘트 일체 금지!

[출력 형식 - 아래 구분자를 정확히 지켜주세요]
TOPIC_TITLE: [오늘의 핵심 논쟁 주제 한 줄]
PHOTO_KEYWORD: [이 논쟁과 직결된 영문 도시/랜드마크 키워드 (예: Paris, Swiss Alps, Rome, Osaka, Tokyo, Flight)]
---THREADS_POST_START---
[여기에 쓰레드에 바로 복사해서 올릴 본문 텍스트 전체를 작성하세요]
---THREADS_POST_END---
"""

    res_text = generate_with_gemini(client, prompt)

    topic_title = "오늘의 여행 밸런스 토론"
    photo_keyword = "Paris"
    threads_post = ""

    t_match = re.search(r"TOPIC_TITLE:\s*(.+)", res_text)
    if t_match:
        topic_title = t_match.group(1).strip()

    p_match = re.search(r"PHOTO_KEYWORD:\s*(.+)", res_text)
    if p_match:
        photo_keyword = p_match.group(1).strip().strip("[]").strip('"')

    c_match = re.search(
        r"---THREADS_POST_START---([\s\S]*?)---THREADS_POST_END---", res_text
    )
    if c_match:
        threads_post = c_match.group(1).strip()
    else:
        threads_post = re.sub(
            r"^(TOPIC_TITLE|PHOTO_KEYWORD):.*$", "", res_text, flags=re.MULTILINE
        ).strip()

    photo_url = match_photo_url(f"{photo_keyword} {topic_title}")

    return {
        "topic": topic_title,
        "photo_keyword": photo_keyword,
        "photo_url": photo_url,
        "threads_post": threads_post,
    }


def send_to_telegram(data: dict) -> None:
    """스마트폰 텔레그램으로 고화질 사진과 복사용 텍스트를 전송합니다."""
    # 1. 고화질 사진 전송 (sendPhoto)
    photo_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    caption_intro = (
        f"📸 [오늘의 쓰레드 논쟁/토론 픽]\n"
        f"🔥 주제: {data['topic']}\n\n"
        f"💡 사진 꾹 눌러 저장 ➔ 아래 글 복사 ➔ 쓰레드에 붙여넣기!\n"
        f"(댓글 유도 효과 극대화 포맷입니다)"
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
    print("1. 쓰레드 댓글 폭발용 논쟁/밸런스형 여행 피드 생성 중...")
    data = create_debate_travel_content()
    print(f"   -> 주제: {data['topic']}")
    print(f"   -> 키워드: {data['photo_keyword']}")
    print(f"   -> 사진 URL: {data['photo_url']}")

    print("2. 텔레그램으로 고화질 사진 및 복사용 텍스트 전송 중...")
    send_to_telegram(data)

    print("3. 이력 저장 중...")
    save_history(data["topic"])
    print("완료! 스마트폰 텔레그램 봇 채팅방을 확인하세요.")


if __name__ == "__main__":
    main()
