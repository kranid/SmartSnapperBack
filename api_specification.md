
# API Specification for SmartSnapper Backend

## Endpoint: `/checkSnapshot`

*   **Method:** `POST`
*   **Content-Type:** `application/json`

### Request Body

A JSON object with the following structure:

```json
{
  "prompt": "<string>",
  "image_base64": "<string>"
}
```

*   `prompt`: A detailed text prompt containing instructions for the AI model and a JSON string with the semantic description of the screen.
*   `image_base64`: A base64-encoded string of the screenshot image (JPEG format).

### Success Response (200 OK)

A JSON array of `SnapIssue` objects. Each object has the following structure:

```json
[
  {
    "message": "<string>",
    "rect": {
      "left": <integer>,
      "top": <integer>,
      "right": <integer>,
      "bottom": <integer>
    },
    "path": "<string>"
  }
]
```

*   `message`: A description of the accessibility issue found.
*   `rect`: An object representing the bounding box of the element with the issue.
*   `path`: An optional path to the UI element.

### Error Response (4xx/5xx)

A JSON object with a `detail` field containing the error message.

```json
{
  "detail": "<string>"
}
```
