# HANDOFF - airflow-ice 프로젝트 인수인계

> 마지막 업데이트: 2026-03-08
> GitHub: https://github.com/seonghyeon-dev/airflow-ice (private)
> Claude Code 세션 이름: `airflow-k8s-setup` (resume: `claude -r airflow-k8s-setup`)

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
| MinIO 배포 | ✅ 완료 | 256MB 제한, 버킷(iceberg-warehouse, spark-logs), Console http://localhost:9001 |
| Spark Operator 설치 | ✅ 완료 | Helm chart 2.4.0, controller + webhook Running |
| Hive Metastore 배포 | ❌ 실패 | 아래 "해결 필요한 이슈" 참고 |
| 커스텀 Spark 이미지 | 🔲 미시작 | Spark 4.0.2 + Iceberg 1.10.1 예정 |
| Spark History Server | 🔲 미시작 | |
| Airflow 배포 (K8s) | 🔲 미시작 | |
| SparkKubernetesOperator DAG | 🔲 미시작 | |

---

## 현재 K8s 클러스터 상태 (2026-03-08 기준)

```
NAMESPACE   NAME                                      READY   STATUS
airflow     postgres-6cbd9d4cd9-5dbw2                 1/1     Running          ✅
metastore   hive-metastore-84884fd7df-5hhcl           0/1     CrashLoopBackOff ❌ (재시작 41+회)
spark       spark-operator-controller-...             1/1     Running          ✅
spark       spark-operator-webhook-...                1/1     Running          ✅
storage     minio-59678d7559-f6h5j                    1/1     Running          ✅
storage     minio-init-buckets-kzvp6                  0/1     Completed        ✅
```

---

## 해결 필요한 이슈 (즉시 처리)

### Hive Metastore 3.1.3 배포 실패

**증상**: Pod CrashLoopBackOff, DB 스키마 초기화 실패 (Derby fallback)

**원인**: Hive 3.x는 `hive-site.xml`을 설정 파일로 사용하는데, 현재 ConfigMap이 `metastore-site.xml`로 마운트되어 있음 → JDBC 연결이 Derby 기본값으로 떨어짐

**해결 방법**:

1. `hive-metastore/k8s/deployment.yaml` 수정:
   - ConfigMap data key: `metastore-site.xml` → `hive-site.xml`
   - volumeMount mountPath: `/opt/hive/conf/metastore-site.xml` → `/opt/hive/conf/hive-site.xml`
   - volumeMount subPath: `metastore-site.xml` → `hive-site.xml`

2. metastore DB 재생성 (잘못된 Derby 스키마 제거):
   ```bash
   # HMS 스케일 다운
   kubectl scale deploy hive-metastore -n metastore --replicas=0

   # PostgreSQL에서 metastore DB 재생성
   kubectl exec -n airflow deploy/postgres -- psql -U airflow -c \
     "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='metastore';"
   kubectl exec -n airflow deploy/postgres -- psql -U airflow -c "DROP DATABASE metastore;"
   kubectl exec -n airflow deploy/postgres -- psql -U airflow -c "CREATE DATABASE metastore;"

   # 수정된 deployment 적용
   kubectl apply -f hive-metastore/k8s/deployment.yaml
   kubectl rollout status deploy/hive-metastore -n metastore
   ```

---

## 다음 단계 (우선순위 순)

### 1. Hive Metastore 배포 수정 (즉시)
- [ ] `hive-metastore/k8s/deployment.yaml`에서 `metastore-site.xml` → `hive-site.xml` 변경
- [ ] metastore DB 재생성
- [ ] Pod 재배포 및 정상 동작 확인 (`kubectl logs -n metastore deploy/hive-metastore`)

### 2. 커스텀 Spark 이미지 빌드
- [ ] `spark/Dockerfile` 작성 (apache/spark:4.0.2 + Iceberg 1.10.1 + AWS SDK)
- [ ] 이미지 빌드: `docker build -t spark-iceberg:local spark/`
- [ ] kind에 로드: `kind load docker-image spark-iceberg:local --name airflow-ice`

### 3. Spark History Server 배포
- [ ] `spark/history-server/deployment.yaml` + `service.yaml` 작성
- [ ] MinIO의 `spark-logs` 버킷 연동 (s3a://spark-logs)
- [ ] NodePort 30180 → localhost:18080

### 4. Airflow 배포 (K8s)
- [ ] `helm/airflow-values.yaml` 작성 (KubernetesExecutor, NodePort 30080)
- [ ] `helm repo add apache-airflow https://airflow.apache.org`
- [ ] Helm으로 설치: `helm install airflow apache-airflow/airflow -n airflow -f helm/airflow-values.yaml`
- [ ] DAG hostPath 마운트 확인 (kind extraMounts → Pod hostPath)

### 5. Airflow S3 Connection 설정
- [ ] MinIO endpoint를 Airflow Connection으로 등록
- [ ] endpoint: `http://minio.storage.svc.cluster.local:9000`
- [ ] 계정: minioadmin / minioadmin

### 6. SparkKubernetesOperator DAG 작성
- [ ] `dags/spark_iceberg_dag.py` 작성
- [ ] `spark/applications/` SparkApplication 템플릿 작성
- [ ] Iceberg 테이블 생성 → 데이터 적재 엔드투엔드 테스트

### 7. 자동화 및 정리
- [ ] `scripts/setup-local.sh` 작성 (kind + helm 원클릭 설치)

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
