"""Export the current FastAPI OpenAPI schema as a shareable Swagger HTML file."""

import json
from pathlib import Path

from main import app


# 실행 위치와 무관하게 저장소 루트의 docs/를 가리킨다.
# 상대 경로로 두면 src/app에서 실행했을 때 src/app/docs/에 엉뚱한 사본이 생긴다.
REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    output = REPO_ROOT / "docs" / "api-reference.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = json.dumps(app.openapi(), ensure_ascii=False, separators=(",", ":"))
    html = f'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{app.title} API 문서</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => SwaggerUIBundle({{
      spec: {schema},
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: [SwaggerUIBundle.presets.apis],
      layout: 'BaseLayout'
    }});
  </script>
</body>
</html>
'''
    output.write_text(html, encoding="utf-8")
    print(output.resolve())


if __name__ == "__main__":
    main()
