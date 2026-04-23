from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
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

# Initialize ChatOpenAI LLM for polza.ai
llm = ChatOpenAI(
    model="anthropic/claude-opus-4.7",
    api_key=POLZA_API_KEY,
    base_url="https://api.polza.ai/api/v1"
)

class CheckSnapshotRequest(BaseModel):
    image_base64: str
    prompt: str

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

@app.post("/checkSnapshot", response_model=List[SnapIssue])
async def check_snapshot(request: CheckSnapshotRequest):
    print("--- /checkSnapshot called ---")
    logger.info("Received request for /checkSnapshot")
    try:
        messages = [
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": request.prompt,
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