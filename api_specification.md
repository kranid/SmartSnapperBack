# API-спецификация SmartSnapper Backend

## Назначение

Метод принимает скриншот экрана и структурированное семантическое описание элементов интерфейса. Сервер сам добавляет текстовую часть промта, отправляет данные в polza.ai и возвращает список найденных проблем доступности.

Клиент не должен отправлять текстовый `prompt`.

## HTTP-запрос

### Endpoint

```http
POST /checkSnapshot
```

Для обратной совместимости также поддерживается `POST /checksnapshot`.

### Headers

Обязательные headers:

```http
Content-Type: application/json
```

Рекомендуемые headers:

```http
Accept: application/json
```

Авторизация со стороны клиента не требуется.

### Body

Body должен быть JSON-объектом.

```json
{
  "snapshotId": "snap-001",
  "platform": "android",
  "capturedAt": "2026-06-10T17:09:39.968Z",
  "snapnodes": [
    {
      "text": "Вернуться назад",
      "actionable": true,
      "role": "button",
      "rect": {
        "left": 11,
        "top": 87,
        "right": 146,
        "bottom": 222
      }
    }
  ],
  "image_base64": "<base64-строка изображения>"
}
```

### Поля body

| Поле | Тип | Обязательное | Описание |
| --- | --- | --- | --- |
| `snapshotId` | `string` | Да | Непустой идентификатор snapshot, сформированный клиентом. |
| `platform` | `string` | Да | Непустое имя платформы. |
| `capturedAt` | `string` | Да | Непустая дата и время создания snapshot в формате ISO 8601. |
| `snapnodes` | `array<object>` | Да | Массив объектов с семантическим описанием элементов экрана. |
| `image_base64` | `string` | Да | Скриншот, закодированный в base64. Нужно передавать только base64-строку, без префикса `data:image/jpeg;base64,`. |

## Объект `snapnode`

`snapnode` - это JSON-объект, описывающий один элемент интерфейса. Сервер не требует жесткой схемы для каждого элемента, но обычно объект может содержать такие поля:

| Поле | Тип | Описание |
| --- | --- | --- |
| `text` | `string` | Текстовая подпись элемента. |
| `rect` | `object` | Координаты элемента на скриншоте. |
| `actionable` | `boolean` | Признак интерактивного элемента. |
| `role` | `string` | Роль элемента, например `button`, `tab`, `check_box`, `edit_text`, `image_button`. |
| `heading` | `boolean` | Признак заголовка. |
| `checked` | `boolean` | Состояние чекбокса или переключателя. |
| `selected` | `boolean` | Признак выбранного элемента. |
| `isselected` | `boolean` | Альтернативное поле для признака выбранного элемента. |
| `roleDescription` | `string` | Текстовое описание роли, если оно есть на клиенте. |
| `stateDescription` | `string` | Текстовое описание состояния, если оно есть на клиенте. |

### Объект `rect`

`rect` описывает координаты элемента на скриншоте.

```json
{
  "left": 11,
  "top": 87,
  "right": 146,
  "bottom": 222
}
```

| Поле | Тип | Описание |
| --- | --- | --- |
| `left` | `integer` | Левая координата элемента. |
| `top` | `integer` | Верхняя координата элемента. |
| `right` | `integer` | Правая координата элемента. |
| `bottom` | `integer` | Нижняя координата элемента. |

## Успешный HTTP-ответ

### Status

```http
201 Created
```

### Headers

```http
Content-Type: application/json
```

### Body

Body содержит сведения о завершённой задаче и массив `violations`. Если проблем нет, `violations` равен пустому массиву `[]`.

```json
{
  "taskId": "task-7dce4fb9-5464-4fa5-a78a-c98cd15cbf96",
  "snapshotId": "snap-001",
  "status": "completed",
  "violations": [
    {
      "message": "property heading must be true",
      "rect": {
        "left": 202,
        "top": 77,
        "right": 703,
        "bottom": 232
      },
      "path": ""
    }
  ]
}
```

### Поля ответа

| Поле | Тип | Описание |
| --- | --- | --- |
| `taskId` | `string` | Сформированный сервером идентификатор задачи. |
| `snapshotId` | `string` | Идентификатор из запроса. |
| `status` | `string` | Для успешного синхронного ответа имеет значение `completed`. |
| `violations` | `array<object>` | Список найденных нарушений с полями `message`, `rect` и `path`. |

## HTTP-ответ с ошибкой

При ошибке сервер возвращает единый JSON-объект:

```json
{
  "message": ["Описание ошибки"],
  "error": "Unprocessable Entity",
  "statusCode": 422
}
```

Возможные статусы:

| Status | Когда возникает |
| --- | --- |
| `422 Unprocessable Entity` | Неверный формат body, отсутствует обязательное поле или изображение не является поддерживаемым Base64. |
| `502 Bad Gateway` | Ответ модели не соответствует ожидаемому JSON-контракту. |
| `500 Internal Server Error` | Внутренняя ошибка сервера или ошибка при обращении к polza.ai. |
| Другой HTTP-статус | Может быть возвращен, если polza.ai вернул ошибку и сервер пробросил ее клиенту. |

## Пример HTTP-запроса через curl

```bash
curl -X POST "http://localhost:8000/checkSnapshot" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "snapshotId": "snap-001",
    "platform": "android",
    "capturedAt": "2026-06-10T17:09:39.968Z",
    "snapnodes": [
      {
        "text": "Вернуться назад",
        "actionable": true,
        "role": "button",
        "rect": {
          "left": 11,
          "top": 87,
          "right": 146,
          "bottom": 222
        }
      },
      {
        "text": "Настроить разделы",
        "heading": true,
        "rect": {
          "left": 202,
          "top": 77,
          "right": 703,
          "bottom": 232
        }
      }
    ],
    "image_base64": "<base64-строка изображения>"
  }'
```

## Пример запроса на Python

```python
import base64
import json

import requests

url = "http://localhost:8000/checkSnapshot"

with open("tests/screenshot.jpg", "rb") as file:
    image_base64 = base64.b64encode(file.read()).decode("utf-8")

payload = {
    "snapshotId": "snap-001",
    "platform": "android",
    "capturedAt": "2026-06-10T17:09:39.968Z",
    "snapnodes": [
        {
            "text": "Вернуться назад",
            "actionable": True,
            "role": "button",
            "rect": {
                "left": 11,
                "top": 87,
                "right": 146,
                "bottom": 222,
            },
        }
    ],
    "image_base64": image_base64,
}

response = requests.post(
    url,
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
    },
    json=payload,
)
response.raise_for_status()

print(json.dumps(response.json(), ensure_ascii=False, indent=2))
```
