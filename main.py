from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List
import base64
import os
from dotenv import load_dotenv
import json
import logging
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

if not POLZA_API_KEY:
    raise ValueError("POLZA_API_KEY environment variable not set.")

PROMPT_TEXT = """
Я предоставлю тебе скриншот экрана и его семантическое описание в json .
Твоя задача выявить все значимые элементы экрана, кнопки, вкладки, заголовки, текстовые поля и чекбоксы на скриншоте и убедиться, что их семантика корректно определена в семантическом описании.
Если ты обнаруживаешь ошибки в семантике, ты должен предоставить описание этих ошибок в виде json с массивом объектов.
Каждый объект должен содержать следующие свойства:
message - сообщение об ошибке
объект rect с  координатами элемента, в котором была обнаружена ошибка,
Убедись, что в объекте rect указаны все четыре координаты: left, top, right, bottom.
В качестве примера используй следующий массив:
[
{
    "message": "property heading must be true ",
    "rect": {
    "left": 48,
    "top": 128,
    "right": 593,
    "bottom": 209
},

},
{
    "message": "property role must by button",
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

# Initialize ChatOpenAI LLM for polza.ai
llm = ChatOpenAI(
    model="google/gemini-3.1-pro-preview-customtools",
    api_key=POLZA_API_KEY,
    base_url="https://api.polza.ai/api/v1"
)

SnapNode = Dict[str, Any]

class CheckSnapshotRequest(BaseModel):
    image_base64: str
    snapnodes: List[SnapNode] = Field(..., description="Structured semantic description of the screen.")

class SnapRect(BaseModel):
    left: int = Field(default=-1, description="The left coordinate of the bounding box.")
    top: int = Field(default=-1, description="The top coordinate of the bounding box.")
    right: int = Field(default=-1, description="The right coordinate of the bounding box.")
    bottom: int = Field(default=-1, description="The bottom coordinate of the bounding box.")

class SnapIssue(BaseModel):
    message: str = Field(..., description="A description of the accessibility issue found.")
    rect: SnapRect = Field(..., description="The bounding box of the element with the issue.")
    path: str = Field(default="", description="An optional path to the UI element.")

class SnapIssueList(BaseModel):
    "A list of accessibility issues found on the screen."
    issues: List[SnapIssue] = Field(..., description="A list of SnapIssue objects.")


# Bind the schema to the model using with_structured_output
structured_llm = llm.with_structured_output(SnapIssueList)

def build_prompt(snapnodes: List[SnapNode]) -> str:
    return (
        PROMPT_TEXT
        + SNAPNODES_PROMPT_PREFIX
        + json.dumps(snapnodes, ensure_ascii=False, indent=2)
    )

@app.post("/checkSnapshot", response_model=List[SnapIssue])
async def check_snapshot(request: CheckSnapshotRequest):
    print("--- /checkSnapshot called ---")
    logger.info("Received request for /checkSnapshot")
    try:
        prompt = build_prompt(request.snapnodes)
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
                            "url": f"data:image/jpeg;base64,{request.image_base64}"
                        },
                    },
                ]
            ),
        ]

        logger.info("Invoking structured_llm with the provided messages.")
        # Invoke the LLM with structured output
        ai_response = structured_llm.invoke(messages)
        logger.info("Successfully received response from structured_llm.")
        
        return ai_response.issues

    except HTTPError as e:
        logger.error(f"HTTPError from polza.ai API: {e}", exc_info=True)
        if e.response is not None:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        else:
            raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
