from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal
import base64
import os
from dotenv import load_dotenv
import json
import logging
import uuid
from http import HTTPStatus
from openai import APIStatusError
from pydantic import ValidationError
from requests.exceptions import HTTPError

print("--- SCRIPT START ---")

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Get Polza.ai API key from environment variable
POLZA_API_KEY = os.getenv("POLZA_API_KEY")
MODEL_TIMEOUT_SECONDS = float(os.getenv("MODEL_TIMEOUT_SECONDS", "120"))

if not POLZA_API_KEY:
    raise ValueError("POLZA_API_KEY environment variable not set.")
if MODEL_TIMEOUT_SECONDS <= 0:
    raise ValueError("MODEL_TIMEOUT_SECONDS must be greater than zero.")

PROMPT_TEXT = """
Я предоставлю тебе скриншот экрана и его семантическое описание в json .
Твоя задача выявить все значимые элементы экрана, кнопки, вкладки, заголовки, текстовые поля и чекбоксы на скриншоте и убедиться, что их семантика корректно определена в семантическом описании.
Если ты обнаруживаешь ошибки в семантике, ты должен предоставить описание этих ошибок в виде json с массивом объектов.
Каждый объект должен содержать следующие свойства:
message - краткое описание обнаруженной проблемы,
recommendation - конкретная рекомендация, как исправить проблему,
объект rect с  координатами элемента, в котором была обнаружена ошибка,
Убедись, что в объекте rect указаны все четыре координаты: left, top, right, bottom.
В качестве примера используй следующий массив:
[
{
    "message": "property heading must be true ",
    "recommendation": "Set heading=true for this heading element.",
    "rect": {
    "left": 48,
    "top": 128,
    "right": 593,
    "bottom": 209
},

},
{
    "message": "property role must by button",
    "recommendation": "Set role=button for this actionable element.",
    "rect": {
    "left": 960,
    "top": 129,
    "right": 1080,
    "bottom": 273
},
    "
}]
ты должен стараться не пропустить ни один элемент.
Тщательно проанализируй скриншот, если недостаточно информации сопоставь элементы с их семантикой.
После анализа элементов перепроверь свои выводы.
в семантическом описание должны соблюдаться все правила ниже:
у любого элемента должно быть свойство текст содержащее подпись для элемента.
Подпись должна передавать смысл назначение и все нюансы элемента.

Когда нет свойства текст предложи  его содержание в сообщении об ошибке.
Если у элемента установлено свойство actionable=true, у него должно быть определено свойство role. Role должно иметь значение, которое передает тип элемента. Для Role возможны следующие значения:   "button", "tab", "check_box", "edit_text", "image_button". роли "button" и "image_button" взаимозаменяемы. Определи по скриншоту тип элемента и предложи правильное значение свойство role в сообщение об ошибке.
Если у элемента нет свойства actionable ему не нужно свойство role.
Если элемент выделен, то у него должно быть свойство isselected=true
У всех заголовков должен быть установлено свойство heading=true.
Убедись, что элемент действительно является заголовком.
role="header" нет.
 - Если визуальный элемент в описании разделяется на несколько элементов, их нужно объединить и присвоить им общее свойство `text` и `role`.
Перепроверь типы элементов и их роли. Убедись, что роли установлены корректно.
""".strip()

SNAPNODES_PROMPT_PREFIX = "\n\nВот семантическое описание в json, которое нужно проанализировать:\n"
RESPONSE_FORMAT_PROMPT = """

Верни только валидный JSON без markdown и без поясняющего текста.
Формат ответа:
[
  {
    "message": "описание проблемы",
    "recommendation": "конкретное исправление проблемы",
    "rect": {
      "left": 0,
      "top": 0,
      "right": 0,
      "bottom": 0
    },
    "path": ""
  }
]
Если проблем нет, верни пустой массив [].
""".strip()

# Initialize ChatOpenAI LLM for polza.ai
check_snapshot_llm = ChatOpenAI(
    model="openai/gpt-6.1-terra",
    api_key=POLZA_API_KEY,
    base_url="https://api.polza.ai/api/v1",
    timeout=MODEL_TIMEOUT_SECONDS,
    max_retries=0,
)

SnapNode = Dict[str, Any]

class ImagePayloadError(ValueError):
    pass

class AIResponseFormatError(ValueError):
    pass

class CheckSnapshotRequest(BaseModel):
    snapshotId: str = Field(..., min_length=1, description="Client-generated snapshot identifier.")
    image_base64: str
    platform: str = Field(..., min_length=1)
    capturedAt: str = Field(..., min_length=1, description="ISO-8601 capture timestamp.")
    snapnodes: List[SnapNode] = Field(..., description="Structured semantic description of the screen.")

class SnapRect(BaseModel):
    left: int = Field(..., description="The left coordinate of the bounding box.")
    top: int = Field(..., description="The top coordinate of the bounding box.")
    right: int = Field(..., description="The right coordinate of the bounding box.")
    bottom: int = Field(..., description="The bottom coordinate of the bounding box.")

class SnapIssue(BaseModel):
    message: str = Field(..., description="A description of the accessibility issue found.")
    recommendation: str = Field(..., description="A concrete recommendation for fixing the accessibility issue.")
    rect: SnapRect = Field(..., description="The bounding box of the element with the issue.")
    path: str = Field(default="", description="An optional path to the UI element.")

class CheckSnapshotResponse(BaseModel):
    taskId: str
    snapshotId: str
    status: Literal["completed"] = "completed"
    violations: List[SnapIssue]

def build_prompt(snapnodes: List[SnapNode]) -> str:
    return (
        PROMPT_TEXT
        + "\n\n"
        + RESPONSE_FORMAT_PROMPT
        + SNAPNODES_PROMPT_PREFIX
        + json.dumps(snapnodes, ensure_ascii=False, indent=2)
    )

def image_base64_to_data_url(image_base64: str) -> str:
    value = image_base64.strip()
    if value.startswith("data:image/"):
        _, separator, value = value.partition(",")
        if not separator:
            raise ImagePayloadError("image_base64 data URL must contain a comma separator.")
        value = value.strip()

    try:
        image_bytes = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ImagePayloadError("image_base64 must be valid base64.") from exc

    if image_bytes.startswith(b"\xff\xd8\xff"):
        mime_type = "image/jpeg"
    elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        mime_type = "image/png"
    elif image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        mime_type = "image/gif"
    elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        mime_type = "image/webp"
    else:
        raise ImagePayloadError("Unsupported image format. Expected JPEG, PNG, GIF, or WEBP.")

    return f"data:{mime_type};base64,{value}"

def response_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)

def parse_json_from_text(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(cleaned):
            if char not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(cleaned[index:])
                return parsed
            except json.JSONDecodeError:
                continue
        raise

def parse_ai_issues_response(content: Any) -> List[SnapIssue]:
    parsed = parse_json_from_text(response_content_to_text(content))

    if isinstance(parsed, dict):
        issues = parsed.get("issues")
    else:
        issues = parsed

    if not isinstance(issues, list):
        raise AIResponseFormatError("AI response must be a JSON array or an object with an 'issues' array.")

    return [SnapIssue(**issue) for issue in issues]

def api_status_error_detail(error: APIStatusError) -> str:
    response = getattr(error, "response", None)
    if response is not None:
        try:
            return response.text
        except Exception:
            pass
    return str(error)

def check_snapshot_error(status_code: int, message: str) -> JSONResponse:
    try:
        error = HTTPStatus(status_code).phrase
    except ValueError:
        error = "Error"
    return JSONResponse(
        status_code=status_code,
        content={"message": [message], "error": error, "statusCode": status_code},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, error: RequestValidationError):
    if request.url.path.casefold() != "/checksnapshot":
        return await request_validation_exception_handler(request, error)

    messages = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
        message = item.get("msg", "Invalid request")
        messages.append(f"{location}: {message}" if location else message)
    return JSONResponse(
        status_code=422,
        content={"message": messages, "error": HTTPStatus(422).phrase, "statusCode": 422},
    )


@app.post("/checksnapshot", response_model=CheckSnapshotResponse, status_code=201)
@app.post("/checkSnapshot", response_model=CheckSnapshotResponse, status_code=201)
async def check_snapshot(request: CheckSnapshotRequest, http_request: Request):
    print("--- /checkSnapshot called ---")
    logger.info("Received request for /checkSnapshot")
    logger.info("X-Debug-Client: %s", http_request.headers.get("x-debug-client", "not set"))
    try:
        prompt = build_prompt(request.snapnodes)
        image_data_url = image_base64_to_data_url(request.image_base64)
        messages = [
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        },
                    },
                ]
            ),
        ]

        logger.info("Invoking llm with the provided messages.")
        ai_response = check_snapshot_llm.invoke(messages)
        logger.info("Successfully received response from llm.")
        
        return CheckSnapshotResponse(
            taskId=f"task-{uuid.uuid4()}",
            snapshotId=request.snapshotId,
            violations=parse_ai_issues_response(ai_response.content),
        )

    except ImagePayloadError as e:
        logger.warning("Invalid checkSnapshot request: %s", e)
        return check_snapshot_error(422, str(e))

    except (json.JSONDecodeError, ValidationError, AIResponseFormatError) as e:
        logger.error("Invalid JSON response from polza.ai: %s", e, exc_info=True)
        return check_snapshot_error(502, "Invalid JSON response from polza.ai.")

    except APIStatusError as e:
        status_code = e.status_code or 500
        logger.error("APIStatusError from polza.ai API: %s", e, exc_info=True)
        return check_snapshot_error(status_code, api_status_error_detail(e))

    except HTTPError as e:
        logger.error(f"HTTPError from polza.ai API: {e}", exc_info=True)
        if e.response is not None:
            return check_snapshot_error(e.response.status_code, e.response.text)
        else:
            return check_snapshot_error(500, str(e))

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return check_snapshot_error(500, f"An unexpected error occurred: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
