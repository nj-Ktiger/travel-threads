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

# 쓰레드에서 3초 만에 읽히고 댓글 터지는 5대 테마
ENGAGEMENT_THEMES = [
    {
        "type": "1 vs 2 호불호 극단 논쟁",
        "desc": "낭만 원탑 vs 환상 와장창 (파리 에펠탑 낭만 vs 소매치기/지린내, 발리 천국 vs 더위/트래픽, 런던 인생도시 vs 최악의 물가 등)",
    },
    {
        "type": "가성비 & 돈값 논쟁",
        "desc": "스위스 융프라우 왕복 25만원 티켓 돈값 한다 vs 그냥 인터라켄 호수가 낫다, 비즈니스석 살 돈으로 5성급 호텔 vs 비행기 피로 줄이기 등",
    },
    {
        "type": "여행 매너 & 밸런스 게임",
        "desc": "비행기 이코노미석 등받이 젖히기 내 권리다 vs 뒷사람 민폐다, 1분 단위 엑셀 계획 J vs 무계획 몸만 오는 P 등",
    },
    {
        "type": "사이다 3줄 팩폭/꿀팁 요약",
        "desc": "유럽 배낭여행 챙겨서 제일 후회한 짐 3가지, 다낭/동남아 여행 솔직히 거품인 쇼핑템 3가지, 일본 여행 편의점에서 현지인만 집는 3가지 등",
    },
    {
        "type": "경험자 1위 참견 유도",
        "desc": "돈키호테에서 사고 집 와서 제일 후회한 거 1위, 동남아 야시장 갔을 때 제일 어이없었던 순간 등",
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
    if any(k in kw for k in ["kyoto", "교토", "후쿠오카", "일본", "돈키호테", "편의점"]):
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
    if any(k in kw for k in ["flight", "airport", "비행기", "공항", "항공", "등받이", "여권", "좌석", "캐리어", "배낭", "backpacking", "luggage"]):
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
    쓰레드에서 3초 만에 읽히고 댓글/저장이 폭발하는 초간결 피드 글을 생성합니다.
    (주저리주저리 긴 설명 일체 배제, 100~160자 내외, 시원한 줄바꿈)
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    history = load_history()

    theme = random.choice(ENGAGEMENT_THEMES)
    recent_summary = "\n".join([f"- {h}" for h in history[-8:]])

    prompt = f"""
당신은 인스타그램 쓰레드(Threads)에서 댓글 수백 개를 터뜨리는 트렌디한 여행 크리에이터입니다.
절대 블로그처럼 주저리주저리 설명하거나 긴 문장을 쓰지 마세요.
읽는 데 3~5초도 안 걸리게, 줄바꿈을 시원하게 넣고 툭툭 던지는 짧고 강렬한 호흡이어야 합니다.

오늘 다룰 테마: [{theme['type']} - {theme['desc']}]

[최근 다룬 주제들 - 중복 피할 것]
{recent_summary}

[쓰레드 핵심 작성 규칙]
1. 분량: 공백 포함 100~160자 내외 (절대 길어지면 안 됨! 총 4~6줄 내외)
2. 사족 제거: 서론, 배경 설명, 훈계, 혼잣말 절대 금지.
3. 네이버 블로그 말투(잇님들, 서이추, ~했답니다, 포스팅 등) 일체 금지!
4. 문체: 담백하고 트렌디한 인스타/쓰레드 구어체 (~함?, ~인가요?, 솔직히, 님들, 1위는?, 인정?)
5. 아래 2가지 포맷 중 테마에 가장 잘 어울리는 1가지를 택해 작성하세요:

[포맷 1: 1 vs 2 극단 밸런스 토론]
1~2줄: 한눈에 꽂히는 질문
1. 의견 A (1줄)
vs
2. 의견 B (1줄)
댓글 유도 질문 1줄

(예시 1)
솔직히 파리 여행…
낭만 원탑이다 vs 환상 와장창이다?

1. 에펠탑 하나로 인생 여행지 등극
vs
2. 소매치기에 지린내 때문에 다신 안 감

다녀오신 분들 솔직히 어떠셨나요?

[포맷 2: 사이다 3줄 팩폭 / 꿀팁 요약]
1~2줄: 뼈 때리는 질문이나 호기심 자극
1. 첫 번째 요약 (1줄)
2. 두 번째 요약 (1줄)
3. 세 번째 요약 (1줄)
공감/댓글 유도 1줄

(예시 2)
유럽 배낭여행 갈 때
제발 이것만은 버리고 가라 3가지

1. 드라이기 (전압 안 맞으면 바로 고장남)
2. 수건 5장 (그냥 호텔/호스텔 거 쓰세요)
3. 챙겨온 책 (짐만 되고 1페이지도 안 읽음)

님들은 가져갔다가 제일 후회한 짐 뭐임?

[출력 형식 - 아래 구분자를 정확히 지켜주세요]
TOPIC_TITLE: [오늘의 핵심 주제 한 줄]
PHOTO_KEYWORD: [어울리는 영문 도시/키워드 (예: Paris, Swiss, Rome, Tokyo, Osaka, Danang, Flight, Backpacking 등)]
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
        f"📸 [오늘의 쓰레드 픽: {data['topic']}]\n\n"
        f"💡 사진 꾹 눌러 저장 ➔ 아래 글 복사 ➔ 쓰레드에 붙여넣기!"
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
    print("1. 쓰레드 초간결 팩폭/논쟁 여행 피드 생성 중...")
    data = create_debate_travel_content()
    print(f"   -> 주제: {data['topic']}")
    print(f"   -> 키워드: {data['photo_keyword']}")
    print(f"   -> 사진 URL: {data['photo_url']}")
    print(f"   -> 본문:\n{data['threads_post']}")

    print("2. 텔레그램으로 고화질 사진 및 복사용 텍스트 전송 중...")
    send_to_telegram(data)

    print("3. 이력 저장 중...")
    save_history(data["topic"])
    print("완료! 스마트폰 텔레그램 봇 채팅방을 확인하세요.")


if __name__ == "__main__":
    main()
