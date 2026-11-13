import os
import random
import re
import sys
import requests
from google import genai
from google.genai.errors import APIError

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()

HISTORY_FILE = "history_topics.txt"

# 쓰레드에서 '진짜 사람'처럼 보여서 댓글/알고리즘이 잘 붙는 4가지 자연스러운 컨셉
HUMAN_STYLES = [
    {
        "type": "여행 준비 고민/질문형",
        "desc": "곧 여행 가는데 헷갈리거나 걱정되는 점을 경험자들에게 진짜 물어보는 느낌 (예: 유럽 소매치기 복대 진짜 필수인지, 다낭 호이안 더운데 갈만한지, 환전 얼마나 해가야 하는지 등)",
    },
    {
        "type": "가벼운 현실 공감/넋두리형",
        "desc": "여행 가거나 준비할 때 겪는 사소하지만 공감 100%인 상황 (예: J친구랑 P친구 일정 조율, 비행기 앞사람 등받이, 공항 면세점 참새방앗간, 캐리어 무게 오버 등)",
    },
    {
        "type": "의외의 호불호/솔직 후기 질문형",
        "desc": "남들 다 좋다고 하는데 막상 가보면 호불호 갈린다는 곳/아이템에 대해 진짜인지 물어보기 (예: 돈키호테 필수템 중 거품, 파리 실제 분위기, 융프라우 25만원 가격 값어치 등)",
    },
    {
        "type": "짧고 굵은 실용 꿀팁 툭 던지기",
        "desc": "가르치려 들지 않고 '이거 의외로 진짜 좋더라 / 이건 절대 챙기지 마셈' 식으로 2~3줄 툭 던지는 정보성 글 (예: 다이소 여행 필수템, 일본 편의점 숨은 꿀템, 구글맵 저장 팁 등)",
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


def create_human_threads_content() -> dict:
    """
    AI 티가 전혀 나지 않고, 실제 한국인 쓰레드 유저가 폰으로 툭 적은 것처럼
    자연스럽고 댓글을 부르는 텍스트 전용 쓰레드 글을 생성합니다.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    history = load_history()

    style = random.choice(HUMAN_STYLES)
    recent_summary = "\n".join([f"- {h}" for h in history[-10:]])

    prompt = f"""
당신은 한국 쓰레드(Threads)를 평소 즐겨 쓰는 평범한 2030 여행 좋아인입니다.
오늘 작성할 글 컨셉: [{style['type']} - {style['desc']}]

[최근 다룬 주제들 - 절대 겹치지 않게 새로운 나라/상황으로 고를 것]
{recent_summary}

[절대 지켜야 할 'AI 티 빼기' 규칙]
1. ❌ 절대 금지 포맷:
   - "1. A vs 2. B" 같은 기계적인 번호 매기기/대결 구도 금지! (사람들이 보자마자 AI 봇인 줄 알고 거름)
   - "여러분의 선택은?", "댓글로 알려주세요!", "어떻게 생각하시나요?" 같은 뻔한 AI 마무리 멘트 금지!
   - 이모지(🔥, 💡, ✈️, 📸 등) 남발 금지! (아예 안 쓰거나 많아야 1개)
   - 블로그 말투, 뉴스 말투, "~했답니다", "잇님들" 절대 금지!
2. ⭕ 진짜 사람처럼 쓰는 법:
   - 길이는 2~4문장, 공백 포함 80~140자 내외로 아주 짧고 담백하게.
   - 스마트폰으로 방금 생각나서 툭 적은 듯한 자연스러운 구어체 (~임?, ~나요, ~던데, 솔직히, 진짜).
   - 마지막은 억지 질문이 아니라, 지나가던 경험자가 "어 난 이랬는데!" 하고 자연스럽게 훈수 두고 싶어지는 여운이나 가벼운 물음으로 끝내기.

[진짜 사람 같은 좋은 예시들 - 톤앤매너만 참고하고 내용은 새로 창작할 것]
- 예시 1 (고민형):
  "일본 여행 갔다온 분들한테 진지하게 물어보고 싶은데, 돈키호테에서 다들 뭘 그렇게 한 바구니씩 담는 거임? 난 막상 가면 살 게 휴족시간이랑 컵라면 말고 딱히 없던데 숨은 꿀템 있음?"
- 예시 2 (공감형):
  "친구랑 해외여행 가기로 했는데 걔는 아침 7시부터 일정 빡세게 도는 스타일이고 나는 11시까지 자고 싶은 스타일임.. 아직 출발도 안 했는데 벌써 체력 빠지네 이거 어떻게 타협함?"
- 예시 3 (호불호형):
  "유럽 처음 가는데 소매치기 썰 너무 많아서 벌써 기빨림. 진짜 님들도 막 복대 차고 핸드폰 스트랩 목에 걸고 다니셨음? 그냥 조심만 하면 괜찮은 수준인가"
- 예시 4 (짧은 꿀팁형):
  "해외여행 자주 가는 친구가 추천해줘서 다이소 압축파우치 써봤는데 진짜 신세계네. 겨울옷 넣는데도 기내용 캐리어 하나로 5박 6일 쌉가능함."

[출력 형식 - 아래 구분자를 정확히 지켜주세요]
TOPIC_TITLE: [오늘 다룬 주제 한 줄 요약]
---THREADS_POST_START---
[여기에 쓰레드에 바로 복붙할 본문만 깔끔하게 작성]
---THREADS_POST_END---
"""

    res_text = generate_with_gemini(client, prompt)

    topic_title = "오늘의 여행 쓰레드"
    threads_post = ""

    t_match = re.search(r"TOPIC_TITLE:\s*(.+)", res_text)
    if t_match:
        topic_title = t_match.group(1).strip()

    c_match = re.search(
        r"---THREADS_POST_START---([\s\S]*?)---THREADS_POST_END---", res_text
    )
    if c_match:
        threads_post = c_match.group(1).strip()
    else:
        threads_post = re.sub(
            r"^TOPIC_TITLE:.*$", "", res_text, flags=re.MULTILINE
        ).strip()

    # 혹시라도 따옴표로 감싸져서 나왔으면 제거
    threads_post = threads_post.strip('"').strip("'").strip()

    return {
        "topic": topic_title,
        "threads_post": threads_post,
    }


def send_to_telegram(data: dict) -> None:
    """스마트폰 텔레그램으로 바로 복사해서 올릴 수 있게 텍스트 본문을 전송합니다."""
    msg_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # 안내 헤더 1줄 + 복사용 본문 단독 전송 (원터치 복사가 편하도록 분리 전송)
    header_payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": f"🧵 [오늘의 쓰레드] {data['topic']}\n👇 아래 글만 꾹 눌러 복사해서 사진 없이 그대로 올리세요!",
        "disable_web_page_preview": True,
    }
    requests.post(msg_api, json=header_payload, timeout=15)

    body_payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": data["threads_post"],
        "disable_web_page_preview": True,
    }
    m_resp = requests.post(msg_api, json=body_payload, timeout=15)
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
    print("1. 자연스러운 한국인 쓰레드 피드 생성 중...")
    data = create_human_threads_content()
    print(f"   -> 주제: {data['topic']}")
    print(f"   -> 본문:\n{data['threads_post']}")

    print("2. 텔레그램으로 복사용 텍스트 전송 중...")
    send_to_telegram(data)

    print("3. 이력 저장 중...")
    save_history(data["topic"])
    print("완료! 스마트폰 텔레그램 봇 채팅방을 확인하세요.")


if __name__ == "__main__":
    main()
