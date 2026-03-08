# Project: airflow-ice

## Overview
Apache Airflow 3.1.7 + Spark + Iceberg 로컬 개발/테스트 환경.
kind(K8s in Docker) 클러스터에서 Airflow DAG → Spark Job → Iceberg 테이블 적재 파이프라인을 개발/테스트한다.

## Tech Stack
- **Language:** Python
- **Framework:** Apache Airflow 3.1.7
- **Database:** PostgreSQL 16
- **Executor:** KubernetesExecutor (K8s 환경 전환 예정)
- **Auth:** FabAuthManager (`airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager`)
- **K8s:** kind (Kubernetes in Docker)
- **Spark:** Spark 4.0.2 + Spark Operator 2.4.0 + SparkKubernetesOperator
- **Table Format:** Apache Iceberg (iceberg-spark-runtime-4.0_2.13:1.10.1)
- **Catalog:** Hive Metastore 3.1.3 standalone (PostgreSQL 백엔드)
  - ⚠️ Hive 4.x는 Iceberg 미지원 (`get_table` API 삭제, [#12878](https://github.com/apache/iceberg/issues/12878))
- **Storage:** MinIO (S3 호환) — 로컬/운영 모두 사용, 로컬은 리소스 제한(256MB)

### 기존 (docker-compose, 레퍼런스용 유지)
- **Container:** Docker Compose
- **Executor:** LocalExecutor
- **Redis:** 주석 처리됨 (불필요)

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
| UI | URL | 비고 |
|---|---|---|
| Airflow | http://localhost:8080 | 계정: airflow / airflow |
| MinIO Console | http://localhost:9001 | 버킷/파일 관리 |
| Spark History Server | http://localhost:18080 | Spark Job 실행 로그 |

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

## K8s 환경 아키텍처 (구축 중)

### 버전 호환 매트릭스
| 컴포넌트 | 버전 | 비고 |
|---|---|---|
| K8s (kind) | v1.33.1 | kindest/node 이미지 |
| Spark | 4.0.2 | apache/spark:4.0.2, Scala 2.13 |
| Iceberg Runtime | 1.10.1 | iceberg-spark-runtime-4.0_2.13 |
| Hive Metastore | 3.1.3 | apache/hive:3.1.3 + PostgreSQL JDBC |
| Spark Operator | 2.4.0 | Helm chart |
| MinIO | latest | S3 호환 오브젝트 스토리지 |

### 전체 구조
```
kind 클러스터 (Docker 컨테이너 1개 = K8s 노드)
│
├── namespace: airflow
│   ├── Pod: airflow-webserver
│   ├── Pod: airflow-scheduler
│   └── Pod: airflow-postgresql
│
├── namespace: spark
│   ├── Pod: spark-operator
│   ├── Pod: spark-history-server
│   └── (Spark Job 실행 시 동적 생성)
│       ├── Pod: spark-driver
│       └── Pod: spark-executor-0
│
├── namespace: metastore
│   └── Pod: hive-metastore
│
└── namespace: storage
    └── Pod: minio (S3 호환, 리소스 제한 256MB)
```

### 데이터 흐름
```
Airflow DAG (SparkKubernetesOperator)
  → Spark Operator가 SparkApplication CR 생성
    → Spark Driver/Executor Pod 실행
      → Hive Metastore (thrift://hive-metastore:9083) 에서 메타정보 조회/등록
      → Iceberg 테이블 데이터 읽기/쓰기 (s3a://bucket/iceberg/warehouse)
      → MinIO (S3 호환) — 로컬/운영 동일 경로, endpoint만 다름

Airflow DAG (S3CreateObjectOperator, S3ToLocalFilesystemOperator 등)
  → MinIO (S3 API) 직접 업로드/다운로드
  → Airflow Connection으로 endpoint 관리
```

### DAG 개발 방식 (hostPath 마운트)
- 로컬 `dags/` 디렉토리를 kind 노드 → Airflow Pod에 직접 마운트
- 파일 수정 → 즉시 반영 (docker-compose 볼륨 마운트와 동일한 경험)
- kind extraMounts로 로컬 → 노드 마운트, hostPath Volume으로 노드 → Pod 마운트

```
로컬 dags/ ──extraMounts──▶ kind 노드 /opt/airflow/dags ──hostPath──▶ Airflow Pod
```

### PostgreSQL 인스턴스 재활용
- DB: `airflow` ← Airflow용
- DB: `metastore` ← Hive Metastore용

### 프로젝트 구조 (목표)
```
airflow-ice/
├── dags/
│   └── spark_iceberg_dag.py            # SparkKubernetesOperator DAG
├── spark/
│   ├── applications/
│   │   ├── base/                       # SparkApplication 템플릿
│   │   └── local/                      # 로컬용 오버라이드 (hostPath + HMS 설정)
│   ├── conf/
│   │   └── spark-defaults.conf         # Iceberg/HMS 관련 Spark 설정
│   ├── history-server/
│   │   ├── deployment.yaml             # Spark History Server Pod
│   │   └── service.yaml                # NodePort 30180
│   └── Dockerfile                      # Spark + Iceberg 런타임 이미지
├── hive-metastore/
│   ├── Dockerfile                      # standalone Hive Metastore 3.1.3 이미지
│   ├── metastore-site.xml              # HMS 설정 (PostgreSQL 연결 등, 참고용)
│   │                                   # ⚠️ Hive 3.x는 hive-site.xml 사용 (ConfigMap으로 마운트)
│   └── k8s/
│       ├── deployment.yaml
│       └── service.yaml                # thrift://hive-metastore:9083
├── helm/
│   ├── airflow-values.yaml             # Airflow Helm (KubernetesExecutor)
│   └── spark-operator-values.yaml
├── minio/
│   └── k8s/
│       ├── deployment.yaml             # MinIO Pod (리소스 제한 256MB)
│       └── service.yaml                # minio:9000 (S3 API), minio:9001 (Console)
├── k8s/
│   ├── namespace.yaml                  # airflow, spark, metastore, storage
│   ├── rbac.yaml                       # Airflow SA → Spark CR 권한
│   └── postgres.yaml                   # PostgreSQL Deployment + Service + DB 초기화
├── kind-config.yaml                    # kind 클러스터 설정 (extraMounts 포함)
├── scripts/
│   └── setup-local.sh                  # kind + helm 원클릭 설치
├── docker-compose.yaml                 # (기존, 레퍼런스용 유지)
└── CLAUDE.md
```

### 리소스 제약 (로컬 16GB 기준)
| 컴포넌트 | 예상 메모리 |
|---|---|
| macOS + 기타 | ~4GB |
| kind 클러스터 | ~500MB |
| PostgreSQL (Airflow + HMS 공유) | ~384MB |
| Airflow (Webserver + Scheduler) | ~2GB |
| Spark Operator | ~256MB |
| Hive Metastore | ~512MB |
| MinIO (리소스 제한) | ~256MB |
| Spark History Server | ~512MB |
| Spark Job (Driver + Executor 1개) | ~2GB |
| **합계 / 여유분** | **~10.4GB / ~5.6GB** |

- Spark Executor 1개로 제한
- Spark Driver/Executor 메모리 각 512MB~1GB
- MinIO는 로컬 환경에서도 사용 (DAG 코드 로컬/운영 동일하게 유지하기 위함)

## .gitignore 규칙
```
logs/                 # Airflow 실행 로그
config/airflow.cfg    # 자동 생성되는 설정 파일
__pycache__/          # Python 캐시
*.pyc                 # Python 바이트코드
.env                  # 환경변수 파일 (비밀정보 포함 가능)
```

## Known Issues
- **Hive 4.x + Iceberg 호환 불가**: Hive 4.0.1에서 `get_table` Thrift API 삭제됨. Iceberg가 이 API를 호출하므로 `Invalid method name: 'get_table'` 에러 발생. Hive 3.1.3으로 다운그레이드하여 해결. ([#12878](https://github.com/apache/iceberg/issues/12878))
- **Hive 3.x 설정 파일명**: Hive 3.x는 `metastore-site.xml`이 아닌 `hive-site.xml`을 사용. ConfigMap 마운트 시 주의 필요.

## Important Notes
- Docker Desktop 메모리를 최소 4GB (권장 8GB) 이상으로 설정해야 한다
- CPU 최소 2개 이상 필요 (airflow-init에서 자동 검증)
- 디스크 공간 최소 10GB 이상 권장
- 예제 DAG 로딩은 비활성화 상태 (`LOAD_EXAMPLES: 'false'`)
- 새로 생성된 DAG은 기본적으로 일시 중지 상태로 시작됨 (`DAGS_ARE_PAUSED_AT_CREATION: 'true'`)
- 커스텀 의존성 추가 시 `_PIP_ADDITIONAL_REQUIREMENTS`보다 커스텀 이미지 빌드를 권장
