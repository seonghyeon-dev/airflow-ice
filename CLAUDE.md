# Project: airflow-ice

## Overview
Apache Airflow 3.1.7 DAG 로컬 개발/테스트를 위한 Docker Compose 환경.
LocalExecutor 기반으로 단일 머신에서 DAG 개발, 디버깅, 테스트를 수행한다.

## Tech Stack
- **Language:** Python
- **Framework:** Apache Airflow 3.1.7
- **Database:** PostgreSQL 16
- **Executor:** LocalExecutor (CeleryExecutor에서 변경됨)
- **Auth:** FabAuthManager (`airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager`)
- **Container:** Docker Compose
- **Redis:** 주석 처리됨 (LocalExecutor 사용으로 불필요)

## Project Structure
```
airflow-ice/
├── CLAUDE.md                 # 프로젝트 설명 및 AI 어시스턴트 가이드
├── docker-compose.yaml       # Airflow 공식 docker-compose 기반 (3.1.7)
├── .env                      # AIRFLOW_UID 등 환경변수 (gitignore 대상)
├── .gitignore                # logs/, __pycache__/, .env 등 제외
├── dags/                     # DAG 파일 디렉토리 (자동 인식)
│   └── example_dag.py        # 동작 확인용 샘플 DAG (BashOperator)
├── logs/                     # Airflow 실행 로그 (마운트용, gitignore 대상)
├── plugins/                  # 커스텀 Airflow 플러그인 (마운트용)
└── config/                   # Airflow 설정 파일 (마운트용, airflow.cfg는 gitignore 대상)
```

## Docker Compose Architecture

### 활성 서비스
| 서비스 | 설명 | 포트 | 헬스체크 |
|--------|------|------|----------|
| `postgres` | PostgreSQL 16 데이터베이스 | 내부 전용 | `pg_isready -U airflow` |
| `airflow-apiserver` | Airflow API 서버 (Web UI 포함) | 8080 | `curl /api/v2/version` |
| `airflow-scheduler` | DAG 스케줄러 | 내부 전용 | `curl :8974/health` |
| `airflow-dag-processor` | DAG 파일 파싱/처리 | 내부 전용 | `airflow jobs check` |
| `airflow-init` | DB 마이그레이션 + admin 계정 생성 (1회성) | - | - |
| `airflow-cli` | CLI 디버깅용 (debug 프로필) | - | - |

### 주석 처리된 서비스 (비활성)
- `redis` - CeleryExecutor용 메시지 브로커
- `airflow-worker` - Celery 워커
- `airflow-triggerer` - 비동기 트리거
- `flower` - Celery 모니터링 UI (포트 5555)

### 공통 환경변수 (`x-airflow-common`)
```yaml
AIRFLOW__CORE__EXECUTOR: LocalExecutor
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
AIRFLOW__CORE__LOAD_EXAMPLES: 'false'
AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: 'true'
AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK: 'true'
AIRFLOW_CONFIG: '/opt/airflow/config/airflow.cfg'
```

### 커스터마이즈 가능한 환경변수 (.env 또는 쉘)
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AIRFLOW_IMAGE_NAME` | `apache/airflow:3.1.7` | Airflow Docker 이미지 |
| `AIRFLOW_UID` | `50000` | 컨테이너 내 사용자 ID |
| `AIRFLOW_PROJ_DIR` | `.` | 볼륨 마운트 기본 경로 |
| `_AIRFLOW_WWW_USER_USERNAME` | `airflow` | 관리자 계정 사용자명 |
| `_AIRFLOW_WWW_USER_PASSWORD` | `airflow` | 관리자 계정 비밀번호 |
| `_PIP_ADDITIONAL_REQUIREMENTS` | (빈 문자열) | 추가 pip 패키지 (테스트용만 권장) |

## Commands

### 서비스 관리
```bash
# 초기화 (DB 마이그레이션 + admin 계정 생성) - 최초 1회 실행
docker compose up airflow-init

# 전체 서비스 백그라운드 시작
docker compose up -d

# 전체 서비스 종료
docker compose down

# 전체 서비스 종료 + 볼륨 삭제 (DB 데이터 포함)
docker compose down -v

# 서비스 상태 확인
docker compose ps

# 특정 서비스 로그 확인
docker compose logs -f <서비스명>

# CLI 디버깅 (debug 프로필)
docker compose --profile debug run airflow-cli <command>
```

## Web UI
- **URL:** http://localhost:8080
- **계정:** airflow / airflow

## DAG 개발 가이드

### DAG 파일 위치
- `dags/` 디렉토리에 `.py` 파일을 추가하면 자동으로 인식된다.
- 컨테이너 내부 경로: `/opt/airflow/dags`

### DAG 작성 패턴 (example_dag.py 참고)
```python
from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="my_dag_id",
    description="DAG 설명",
    schedule=None,            # 스케줄 설정 (None = 수동 실행)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["태그"],
) as dag:
    task = BashOperator(
        task_id="task_id",
        bash_command='echo "Hello"',
    )
```

### 기존 DAG 목록
- `example_hello_world` (`dags/example_dag.py`): BashOperator 기반 동작 확인용 샘플. `say_hello` -> `print_date` 순차 실행.

## Code Style Rules
- [x] 커밋 메시지는 한글로 작성
- [x] 결과값과 설명은 무조건 한글로 작성
- [x] 테스트 코드 필수 작성
- [x] DAG 파일에 docstring으로 설명 포함

## .gitignore 규칙
```
logs/                 # Airflow 실행 로그
config/airflow.cfg    # 자동 생성되는 설정 파일
__pycache__/          # Python 캐시
*.pyc                 # Python 바이트코드
.env                  # 환경변수 파일 (비밀정보 포함 가능)
```

## Important Notes
- Docker Desktop 메모리를 최소 4GB (권장 8GB) 이상으로 설정해야 한다
- CPU 최소 2개 이상 필요 (airflow-init에서 자동 검증)
- 디스크 공간 최소 10GB 이상 권장
- 예제 DAG 로딩은 비활성화 상태 (`LOAD_EXAMPLES: 'false'`)
- 새로 생성된 DAG은 기본적으로 일시 중지 상태로 시작됨 (`DAGS_ARE_PAUSED_AT_CREATION: 'true'`)
- 커스텀 의존성 추가 시 `_PIP_ADDITIONAL_REQUIREMENTS`보다 커스텀 이미지 빌드를 권장
