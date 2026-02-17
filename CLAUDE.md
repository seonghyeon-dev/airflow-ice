# Project: test-airflow

## Overview
Airflow DAG 로컬 개발/테스트를 위한 Docker Compose 환경

## Tech Stack
- Language: Python
- Framework: Apache Airflow 3.1.7
- Database: PostgreSQL 16
- ~~Message Broker: Redis 7.2~~ (주석 처리됨, LocalExecutor 사용으로 불필요)
- Executor: LocalExecutor (CeleryExecutor에서 변경)
- Container: Docker Compose

## Project Structure
```
airflow-ice/
├── docker-compose.yaml   # Airflow 공식 docker-compose (3.1.7)
├── .env                  # AIRFLOW_UID 등 환경변수
├── dags/                 # DAG 파일 디렉토리
│   └── example_dag.py    # 동작 확인용 샘플 DAG
├── logs/                 # Airflow 로그 (마운트용, gitignore)
├── plugins/              # 커스텀 플러그인 (마운트용)
├── config/               # Airflow 설정 (마운트용)
└── .gitignore            # logs/ 등 제외
```

## Code Style Rules
- [x] 커밋 메시지는 한글로 작성
- [x] 결과값과 설명은 무조건 한글로 작성
- [x] 테스트 코드 필수 작성

## Commands
- `docker compose up airflow-init` - 초기화 (DB 마이그레이션 + admin 계정 생성)
- `docker compose up -d` - 전체 서비스 백그라운드 시작
- `docker compose down` - 전체 서비스 종료
- `docker compose down -v` - 전체 서비스 종료 + 볼륨 삭제
- `docker compose ps` - 서비스 상태 확인
- `docker compose logs -f <서비스명>` - 로그 확인

## Web UI
- URL: http://localhost:8080
- 계정: airflow / airflow

## Important Notes
- Docker Desktop 메모리를 최소 4GB (권장 8GB) 이상으로 설정해야 합니다
- 예제 DAG 로딩은 꺼져 있습니다 (`LOAD_EXAMPLES: 'false'`)
- `dags/` 디렉토리에 DAG 파일을 추가하면 자동으로 인식됩니다
