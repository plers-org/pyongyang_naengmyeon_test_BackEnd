"""Export the current FastAPI OpenAPI schema as a shareable Swagger HTML file."""

import json
from pathlib import Path

from main import app


def main() -> None:
    output = Path("docs/api-reference.html")
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
