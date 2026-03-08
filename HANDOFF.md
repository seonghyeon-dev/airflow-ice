# HANDOFF - airflow-ice 프로젝트 인수인계

> 마지막 업데이트: 2026-02-22
> GitHub: https://github.com/seonghyeon-dev/airflow-ice (private)

## 프로젝트 목표

Airflow DAG → Spark Job (SparkKubernetesOperator) → Iceberg 테이블 적재 파이프라인을
로컬 kind 클러스터에서 개발/테스트할 수 있는 환경 구축.

---

## 완료된 작업

### Phase 1: Docker Compose Airflow 환경 (완료, 현재 종료 상태)
- Airflow 3.1.7 + PostgreSQL 16 + LocalExecutor 환경 구성
- CeleryExecutor → LocalExecutor 변경 (기존 설정은 주석 처리)
- 샘플 DAG 작성 (`dags/example_dag.py`)
- Web UI 접속 확인 (http://localhost:8080)
- GitHub 저장소 생성 및 push
- **현재 상태: `docker compose down`으로 종료됨** (kind 클러스터에 리소스 양보)

### Phase 2: K8s 환경 구축 (진행 중)

| 단계 | 상태 | 비고 |
|------|------|------|
| kind 클러스터 생성 | ✅ 완료 | v1.33.1, extraMounts + 포트매핑(8080,9001,18080) |
| Namespace 생성 | ✅ 완료 | airflow, spark, metastore, storage |
| RBAC 설정 | ✅ 완료 | airflow SA → spark namespace SparkApplication 권한 |
| PostgreSQL 배포 | ✅ 완료 | airflow DB + metastore DB, 384MB 제한 |
| MinIO 배포 | ✅ 완료 | 256MB 제한, 버킷 생성(iceberg-warehouse, spark-logs), Console http://localhost:9001 |
| Spark Operator 설치 | ✅ 완료 | Helm chart 2.4.0, controller + webhook Running |
| Hive Metastore 배포 | ❌ 실패 | 아래 "해결 필요한 이슈" 참고 |
| 커스텀 Spark 이미지 | 🔲 미시작 | Spark 4.0.2 + Iceberg 1.10.1 예정 |
| Spark History Server | 🔲 미시작 | |
| Airflow 배포 (K8s) | 🔲 미시작 | |
| SparkKubernetesOperator DAG | 🔲 미시작 | |

---

## 해결 필요한 이슈 (즉시 처리)

### 1. Hive Metastore 3.1.3 배포 실패
**증상**: Pod CrashLoopBackOff, 스키마 초기화 실패
**원인**: Hive 3.x는 `hive-site.xml`을 설정 파일로 사용하는데, 현재 ConfigMap이 `metastore-site.xml`로 마운트되어 있음 → JDBC 연결이 Derby 기본값으로 떨어짐
**해결 방법**:
1. `hive-metastore/k8s/deployment.yaml`에서 volumeMount 경로를 `metastore-site.xml` → `hive-site.xml`로 변경
2. metastore DB 재생성 (기존 잘못된 스키마 제거)
3. Pod 재배포

```yaml
# 변경 전
mountPath: /opt/hive/conf/metastore-site.xml
subPath: metastore-site.xml

# 변경 후
mountPath: /opt/hive/conf/hive-site.xml
subPath: hive-site.xml
```
ConfigMap의 data key도 `metastore-site.xml` → `hive-site.xml`로 변경 필요.

### 2. Hive 4.x + Iceberg 호환 불가 (해결 완료)
- Hive 4.0.1에서 `get_table` API 삭제 → Iceberg에서 호출 시 에러
- **해결**: Hive 3.1.3으로 다운그레이드 (Dockerfile, deployment 수정 완료)
- 이미지 빌드 및 kind 로드 완료 (`hive-metastore:local`)

---

## 미커밋 변경사항

현재 세션에서 생성/수정된 파일 (모두 미커밋):
- `CLAUDE.md` — 대폭 업데이트 (버전 매트릭스, Known Issues 등)
- `HANDOFF.md` — 인수인계 문서
- `kind-config.yaml` — kind 클러스터 설정
- `k8s/namespace.yaml` — Namespace 정의
- `k8s/rbac.yaml` — RBAC 설정
- `k8s/postgres.yaml` — PostgreSQL 배포
- `hive-metastore/Dockerfile` — Hive 3.1.3 기반
- `hive-metastore/metastore-site.xml` — HMS 설정 (참고용)
- `hive-metastore/k8s/deployment.yaml` — HMS 배포 (⚠️ hive-site.xml 수정 필요)
- `hive-metastore/k8s/service.yaml` — HMS 서비스
- `minio/k8s/deployment.yaml` — MinIO 배포 + 버킷 초기화 Job
- `minio/k8s/service.yaml` — MinIO 서비스 (ClusterIP + NodePort)
- `helm/spark-operator-values.yaml` — Spark Operator Helm values
- `spark/` — 빈 디렉토리 구조 (conf, applications, history-server)

---

## 다음 단계 (우선순위 순)

### 1. Hive Metastore 배포 수정 (즉시)
- [ ] deployment.yaml에서 `metastore-site.xml` → `hive-site.xml` 변경 (ConfigMap key + volumeMount)
- [ ] metastore DB 재생성
- [ ] Pod 재배포 및 정상 동작 확인

### 2. 커스텀 Spark 이미지 빌드
- [ ] `spark/Dockerfile` 작성 (apache/spark:4.0.2 + Iceberg 1.10.1 + AWS SDK)
- [ ] 이미지 빌드 → kind 클러스터에 로드

### 3. Spark History Server 배포
- [ ] `spark/history-server/deployment.yaml` + `service.yaml` 작성
- [ ] MinIO의 spark-logs 버킷 연동
- [ ] NodePort 30180 설정

### 4. Airflow 배포 (K8s)
- [ ] `helm/airflow-values.yaml` 작성 (KubernetesExecutor, NodePort 30080)
- [ ] Helm으로 Airflow 설치
- [ ] DAG hostPath 마운트 확인

### 5. Airflow S3 Connection 설정
- [ ] MinIO endpoint를 Airflow Connection으로 등록

### 6. SparkKubernetesOperator DAG 작성
- [ ] `dags/spark_iceberg_dag.py` 작성
- [ ] `spark/applications/` SparkApplication 템플릿 작성
- [ ] 엔드투엔드 테스트

### 7. 자동화 및 정리
- [ ] `scripts/setup-local.sh` 작성
- [ ] 변경사항 커밋 및 push

---

## 현재 K8s 클러스터 상태

```bash
# 클러스터 확인
kubectl cluster-info --context kind-airflow-ice

# Pod 상태 확인
kubectl get pods -A

# 정상 동작 중인 서비스
# - postgres (airflow ns): Running
# - minio (storage ns): Running
# - spark-operator-controller (spark ns): Running
# - spark-operator-webhook (spark ns): Running

# 문제 있는 서비스
# - hive-metastore (metastore ns): CrashLoopBackOff (hive-site.xml 수정 필요)
```

---

## 핵심 파일 참조

| 파일 | 역할 |
|------|------|
| `CLAUDE.md` | 프로젝트 전체 컨텍스트 (아키텍처, 규칙, 구조, Known Issues) |
| `kind-config.yaml` | kind 클러스터 설정 (extraMounts, 포트매핑) |
| `k8s/namespace.yaml` | Namespace 정의 (airflow, spark, metastore, storage) |
| `k8s/rbac.yaml` | Airflow SA → Spark CR 권한 |
| `k8s/postgres.yaml` | PostgreSQL 배포 (airflow + metastore DB) |
| `hive-metastore/Dockerfile` | HMS 3.1.3 이미지 (PostgreSQL JDBC 포함) |
| `hive-metastore/k8s/deployment.yaml` | HMS 배포 (⚠️ hive-site.xml 수정 필요) |
| `minio/k8s/deployment.yaml` | MinIO 배포 + 버킷 초기화 |
| `helm/spark-operator-values.yaml` | Spark Operator 설정 |
| `docker-compose.yaml` | 기존 Docker Compose (레퍼런스용 유지) |

---

## 주의사항

- 로컬 메모리 16GB 제약 — docker-compose와 kind 동시 실행 비권장
- **Hive 4.x 사용 금지** — Iceberg 미지원 (`get_table` API 삭제)
- Spark 4.0은 **Scala 2.13** 기본 — 아티팩트 선택 시 `_2.13` 확인
- 모든 결과/설명은 한글로 작성 (Code Style Rules)
- 커밋 메시지도 한글
- MinIO 계정: minioadmin / minioadmin
