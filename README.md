# plers services

평양냉면 취향 추천 서비스 백엔드.

취향 테스트 6문항의 답변을 4축 취향 벡터(육향·감칠맛·메밀향·산미)로 변환해, 가게 프로필과 가장 잘 맞는 곳을 추천합니다.

## 구성

| 경로 | 설명 |
| --- | --- |
| `src/app/` | FastAPI 애플리케이션 → [README](src/app/README.md) |
| `test/` | 테스트 |
| `deploy/` | EC2 배포 스크립트, nginx / systemd 설정 |
| `docs/` | PRD 및 API 레퍼런스 |

## 빠른 시작

```bash
cd src/app
pip install -r requirements.txt
uvicorn main:app --reload
```

## 테스트

```bash
PYTHONPATH=src/app pytest test/
```

## 문서

- [PRD: 취향테스트 결과 응답 확장](docs/prd-recommendation-result.md)
- `docs/api-reference.html` — API 레퍼런스
- `docs/aws-deploy-guide.html` — 배포 가이드
