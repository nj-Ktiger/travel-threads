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

# 매일 질리지 않게 번갈아 다룰 매력적인 여행 테마 풀
TRAVEL_THEMES = [
    "한국인에게 덜 알려진 일본 소도시 감성 힐링 여행지",
    "동남아 가성비 최고인 감성 리조트 및 휴양지",
    "주말에 차 타고 훌쩍 떠나기 좋은 국내 숨은 드라이브/힐링 명소",
    "해외여행 갈 때 항공권/호텔/환전에서 10만원 이상 아끼는 실전 꿀팁",
    "여행 짐 싸기 삶의 질 수직상승 시켜주는 여행 필수 꿀템 추천",
    "유럽 자유여행 초보자가 모르면 후회하는 알짜 코스 및 팁",
    "국내 감성 촌캉스 & 불멍하기 좋은 힐링 여행지",
    "부모님 모시고 가거나 연인과 가기 딱 좋은 2박 3일 해외 여행지",
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


def fetch_landmark_photo(search_keyword: str) -> str:
    """Wikimedia Commons 공개 API를 사용하여 해당 여행지의 고화질 사진을 가져옵니다."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{search_keyword} landscape view",
        "gsrnamespace": 6,
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
        "gsrlimit": 3,
    }
    headers = {
        "User-Agent": "TravelThreadsBot/1.0 (https://github.com/nj-Ktiger/travel-threads)"
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.ok:
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                imgs = page.get("imageinfo", [])
                if imgs and imgs[0].get("url"):
                    img_url = imgs[0]["url"]
                    if img_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        return img_url
    except Exception as e:
        print(f"[경고] 사진 검색 실패 ({search_keyword}): {e}")

    # Fallback 기본 고화질 여행 풍경 사진
    return "https://images.unsplash.com/photo-1488646953014-85cb44e25828?auto=format&fit=crop&w=1200&q=80"


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


def create_travel_threads_content() -> dict:
    """쓰레드(Threads)에서 알고리즘을 탈 수 있는 매력적인 바이럴 여행 콘텐츠를 생성합니다."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    history = load_history()

    # 최근에 다루지 않은 테마 무작위 선정
    available_themes = [t for t in TRAVEL_THEMES if t not in history[-len(TRAVEL_THEMES) :]]
    if not available_themes:
        available_themes = TRAVEL_THEMES
    theme = random.choice(available_themes)

    recent_summary = "\n".join([f"- {h}" for h in history[-8:]])

    prompt = f"""
당신은 인스타그램 쓰레드(Threads)에서 10만 팔로워를 보유한 감각적인 2030 여행 크리에이터입니다.
오늘 다룰 메인 테마: [{theme}]

[최근 다룬 주제들 - 중복 피할 것]
{recent_summary}

한국 2030 독자들이 피드를 내리다가 손가락을 멈추고 무조건 [저장] 및 [공유]를 누를 수밖에 없는,
호기심을 자극하고 진짜 실용적인 정보가 담긴 쓰레드(Threads) 전용 피드 글을 작성하세요.

[필수 작성 규칙]
1. 첫 문장 후킹: 궁금증을 폭발시키는 강렬한 한 줄 (예: "여긴 아직 한국인들 잘 모르는...", "일본 n번째 가는 사람만 아는...", "비행기표 살 때 이 버튼 안 끄면 10만원 날립니다")
2. 본문 내용: 3~4개의 명확한 포인트(지명, 특징, 꿀팁)를 이모지와 함께 한눈에 읽히게 구성
3. 말투: 친절하면서도 감각적인 2030 대화체 (~해요, ~해보세요, ~거든요)
4. 저장 유도 문구: "📌 이번 여행 갈 때 꼭 꺼내보게 미리 저장해 두세요!"
5. 프로필 유도 문구: "📍 상세 일정표와 여행기 정리는 프로필 링크 블로그에 적어둘게요!"
6. 글자 수: 쓰레드 1개 피드에 딱 들어가는 350~450자 내외
7. 인기 해시태그 4~5개 포함

[출력 형식 - 아래 구분자를 정확히 지켜주세요]
TOPIC_TITLE: [오늘 다룬 핵심 주제 한 줄 (예: 일본 소도시 우지 힐링 여행)]
PHOTO_SEARCH: [고화질 사진 검색에 쓸 영문 랜드마크 키워드 (예: Uji Kyoto temple, Fukuoka Yanagawa, Da Nang beach)]
---THREADS_POST_START---
[여기에 쓰레드에 복사해서 바로 올릴 본문 텍스트 전체를 작성하세요]
---THREADS_POST_END---
"""

    res_text = generate_with_gemini(client, prompt)

    topic_title = "오늘의 여행 꿀팁"
    photo_search = "Kyoto Japan"
    threads_post = ""

    t_match = re.search(r"TOPIC_TITLE:\s*(.+)", res_text)
    if t_match:
        topic_title = t_match.group(1).strip()

    p_match = re.search(r"PHOTO_SEARCH:\s*(.+)", res_text)
    if p_match:
        photo_search = p_match.group(1).strip()

    c_match = re.search(
        r"---THREADS_POST_START---([\s\S]*?)---THREADS_POST_END---", res_text
    )
    if c_match:
        threads_post = c_match.group(1).strip()
    else:
        threads_post = re.sub(
            r"^(TOPIC_TITLE|PHOTO_SEARCH):.*$", "", res_text, flags=re.MULTILINE
        ).strip()

    photo_url = fetch_landmark_photo(photo_search)

    return {
        "topic": topic_title,
        "photo_url": photo_url,
        "threads_post": threads_post,
    }


def send_to_telegram(data: dict) -> None:
    """스마트폰 텔레그램으로 고화질 사진과 복사용 텍스트를 전송합니다."""
    # 1. 고화질 사진 전송 (sendPhoto)
    photo_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    caption_intro = (
        f"📸 [오늘의 쓰레드 추천 사진]\n"
        f"🏷️ 주제: {data['topic']}\n\n"
        f"💡 위 사진을 꾹 눌러 갤러리에 저장하고,\n"
        f"아래 글을 복사해서 쓰레드에 바로 올리세요! (3초 완성)"
    )

    photo_payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": data["photo_url"],
        "caption": caption_intro,
    }

    try:
        p_resp = requests.post(photo_api, json=photo_payload, timeout=15)
        if not p_resp.ok:
            print(f"[경고] 사진 전송 실패 ({p_resp.status_code}), 텍스트로 계속 진행합니다.")
    except Exception as e:
        print(f"[경고] 사진 전송 오류: {e}")

    # 2. 폰에서 길게 터치 한 번으로 통째로 복사하기 편하게 본문만 단독 전송 (sendMessage)
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
    print("1. 오늘자 바이럴 여행 쓰레드 콘텐츠 생성 중...")
    data = create_travel_threads_content()
    print(f"   -> 선정된 주제: {data['topic']}")
    print(f"   -> 사진 URL: {data['photo_url']}")

    print("2. 스마트폰 텔레그램으로 고화질 사진 및 복사용 텍스트 전송 중...")
    send_to_telegram(data)

    print("3. 이력 저장 중...")
    save_history(data["topic"])
    print("완료! 스마트폰 새 텔레그램 봇 채팅방을 확인하세요.")


if __name__ == "__main__":
    main()
