# Spark Job 설정 튜닝 가이드

## 문서 정보

|항목     |내용             |
|-------|---------------|
|작성일    |2026-03-06     |
|환경     |Kubernetes 클러스터|
|스토리지   |S3 (MinIO)     |
|Spark  |4.1.1          |
|Iceberg|1.10.1         |
|Airflow|3.1.7          |

-----

## 1. 워크플로우 개요

### 1.1 전체 흐름

```
[Oracle DB] → [Airflow DAG] → [S3 텍스트 파일 생성] → [Spark Job 실행 (K8S)] → [Iceberg 테이블 적재] → [Oracle DB 완료 처리]
```

### 1.2 Spark Job 처리 단계

1. S3에 저장된 텍스트 파일 조회 (avro 파일 경로 목록)
1. 해당 경로의 avro 파일들 read
1. Iceberg 테이블에 append

### 1.3 Airflow DAG 처리 단계

1. Oracle DB 테이블에서 처리 대상 조회
1. avro 파일 경로들을 텍스트 파일로 만들어 S3에 저장
1. `SparkKubernetesOperator`를 사용하여 K8S 환경에 Spark Job 실행 (argument: Iceberg 테이블명, 텍스트 파일 경로)
1. 처리 완료 후 Oracle DB 테이블에 해당 row 완료 처리

-----

## 2. Spark 리소스 설정 가이드

### 2.1 설정 항목 요약

|설정                                                      |현재 값   |산정 기준                  |근거 수준       |
|--------------------------------------------------------|-------|-----------------------|------------|
|`driver-cores`                                          |(설정 필요)|아래 가이드 참고              |명확한 기준 필요   |
|`driver-memory`                                         |(설정 필요)|아래 가이드 참고              |명확한 기준 필요   |
|`executor-cores`                                        |(설정 필요)|아래 가이드 참고              |명확한 기준 필요   |
|`executor-memory`                                       |(설정 필요)|아래 가이드 참고              |명확한 기준 필요   |
|`num-executors`                                         |동적 계산  |avro 파일 총 크기 / 70MB + 1|경험적 (테스트 결과)|
|`spark.sql.shuffle.partitions`                          |70     |-                      |명확한 기준 필요   |
|`spark.sql.adaptive.coalescePartitions.parallelismFirst`|true   |-                      |명확한 기준 필요   |

### 2.2 Driver 설정

Driver는 DAG 생성, 태스크 스케줄링, 결과 수집을 담당한다. 현재 워크플로우(avro read → Iceberg append)는 Driver에 대량 데이터를 collect하지 않으므로 상대적으로 작은 리소스로도 충분하다.

**권장 설정:**

|설정             |권장 값   |근거                                              |
|---------------|-------|------------------------------------------------|
|`driver-cores` |1      |단순 스케줄링 작업. collect() 미사용 시 1 core로 충분          |
|`driver-memory`|1g ~ 2g|Spark 공식 문서 기본값 1g. Iceberg 메타데이터 처리를 감안하여 2g 권장|


> **참고:** executor 수가 500개를 초과하는 대규모 잡이 아닌 이상 driver-cores를 늘릴 필요는 없다.

### 2.3 Executor 설정

#### 2.3.1 executor-cores

|설정              |권장 값 |근거                                                                                                     |
|----------------|-----|-------------------------------------------------------------------------------------------------------|
|`executor-cores`|2 ~ 5|Spark 공식 튜닝 가이드에서 권장하는 범위. S3(MinIO) I/O throughput 관점에서 executor당 5개 이하 코어가 최적의 처리량을 보인다는 것이 일반적 가이드라인|

**상세 근거:**

- executor당 코어가 1개(Tiny 방식)이면 JVM 내 멀티태스크 실행의 이점을 살릴 수 없고, broadcast 변수 등이 executor마다 복제되어 메모리 낭비가 발생한다.
- executor당 코어가 너무 많으면(Fat 방식) GC 부담이 증가하고, S3/HDFS 동시 write throughput이 오히려 저하된다.
- **실무적 권장: 2 ~ 4 cores** (현재 워크플로우가 단순 read → append이므로 코어 수를 높게 잡을 필요 없음)

#### 2.3.2 executor-memory

|설정               |권장 값   |근거                                                               |
|-----------------|-------|-----------------------------------------------------------------|
|`executor-memory`|2g ~ 4g|avro read → Iceberg append의 단순 파이프라인. 복잡한 셔플이나 조인이 없으므로 큰 메모리 불필요|

**메모리 구성 참고 (Spark 4.x 기준):**

```
Total Executor Memory = executor-memory + spark.executor.memoryOverhead
                      = executor-memory + max(384MB, executor-memory * 0.1)
```

- `executor-memory`로 설정한 값은 JVM Heap 영역
- Spark은 이 외에 memoryOverhead(기본 10%, 최소 384MB)를 추가 요청
- K8S 환경에서는 Pod 리소스 request에 이 합산 값이 반영됨
- 예: `executor-memory=2g` → 실제 Pod 메모리 요청 ≈ 2g + 384MB ≈ 2.4g

> **주의:** memoryOverhead가 부족하면 K8S에서 OOMKilled가 발생할 수 있다. avro 파일 하나의 크기가 비정상적으로 큰 경우를 대비하여 여유를 두는 것이 좋다.

#### 2.3.3 num-executors (현재 방식)

**현재 산정 공식:**

```
num-executors = (avro 파일들의 총 크기 합 / 70MB) + 1
```

**현재 방식의 배경:**

- 70MB 기준은 경험적 테스트를 통해 적절한 성능이 나오는 것으로 확인되어 결정된 값
- 명확한 이론적 근거가 있는 것은 아니며, 좀 더 체계적인 기준 수립이 필요함

**70MB 기준에 대한 분석:**

- Spark에서 하나의 태스크가 처리하는 데이터 단위는 파티션이며, 파일 기반 소스의 경우 일반적으로 파일 크기 혹은 split size가 파티션 크기를 결정한다.
- Spark의 기본 maxPartitionBytes(`spark.sql.files.maxPartitionBytes`)는 128MB이다.
- 70MB는 128MB보다 작아서 executor당 하나의 파티션을 처리하더라도 메모리 여유가 확보되는 수준이다.
- avro 파일은 read 시 메모리에서 row 형태로 디시리얼라이즈되므로 실제 메모리 사용량은 디스크 크기보다 클 수 있다.

**개선 제안 (근거 기반 산정 방향):**

|접근 방식                   |설명                                      |산정 공식                                                    |
|------------------------|----------------------------------------|---------------------------------------------------------|
|방법 1: 파티션 수 기반          |Spark이 생성하는 실제 파티션 수를 기준으로 executor 수 결정|`num-executors = ceil(total_partitions / executor-cores)`|
|방법 2: 목표 태스크 시간 기반      |태스크당 처리 시간을 측정하여 총 처리 시간 목표에 맞게 조정      |벤치마크 필요                                                  |
|방법 3: Dynamic Allocation|Spark이 런타임에 자동으로 executor 수를 조정         |아래 섹션 참고                                                 |

**방법 1 상세 (권장):**

```
1) total_input_size = avro 파일 총 크기
2) num_partitions = ceil(total_input_size / spark.sql.files.maxPartitionBytes)
   - maxPartitionBytes 기본값: 128MB
3) num_executors = ceil(num_partitions / executor-cores)
   - executor-cores = 2 기준 예시
4) 최소 1, 최대는 K8S 클러스터 가용 리소스 내에서 결정
```

예시: avro 파일 총 크기가 1GB인 경우

- `num_partitions = ceil(1024MB / 128MB) = 8`
- `executor-cores = 2`인 경우: `num_executors = ceil(8 / 2) = 4`

> **TODO:** 위 공식으로 계산한 executor 수와 현재 70MB 기준 방식의 결과를 비교 테스트하여 최적 기준을 확정할 필요가 있다.

-----

## 3. Spark SQL / AQE 설정

### 3.1 Adaptive Query Execution (AQE)

Spark 4.x에서 AQE는 기본 활성화 상태이다. AQE는 런타임 통계를 사용하여 최적의 실행 계획을 선택한다.

|설정                                                      |현재 값|기본값 |설명            |
|--------------------------------------------------------|----|----|--------------|
|`spark.sql.adaptive.enabled`                            |(기본)|true|AQE 활성화 여부    |
|`spark.sql.adaptive.coalescePartitions.enabled`         |(기본)|true|셔플 후 파티션 자동 병합|
|`spark.sql.adaptive.coalescePartitions.parallelismFirst`|true|true|병합 시 병렬성 우선 여부|
|`spark.sql.shuffle.partitions`                          |70  |200 |셔플 시 파티션 수    |

### 3.2 spark.sql.shuffle.partitions 설정 분석

**현재 값: 70**

현재 워크플로우(avro read → Iceberg append)에서 셔플이 발생하는 경우:

- Iceberg의 `write.distribution-mode`가 `hash`(기본값, Iceberg 1.5.0+)인 경우, 파티션 키 기반으로 데이터를 재분배하기 위해 셔플 발생
- `write.distribution-mode=none`이면 셔플이 발생하지 않음

**분석:**

- AQE가 활성화되어 있으면 `spark.sql.shuffle.partitions`는 초기 파티션 수로만 사용되고, 런타임에 AQE가 자동으로 최적 파티션 수로 병합(coalesce)한다.
- `parallelismFirst=true`는 AQE가 파티션을 병합할 때 목표 크기보다 병렬성을 우선시하도록 한다. 이 설정은 파티션당 데이터가 적더라도 더 많은 파티션을 유지하여 병렬 처리를 극대화한다.
- 70은 기본값(200)보다 낮은 수치인데, 데이터 규모가 작은 경우에는 합리적인 값이다. 다만, 데이터가 커지면 너무 적은 초기 파티션이 셔플 단계에서 병목이 될 수 있다.

**개선 제안:**

|데이터 규모     |권장 shuffle.partitions|비고                          |
|-----------|---------------------|----------------------------|
|~ 500MB    |70 (현재)              |현재 규모에 적합                   |
|500MB ~ 5GB|200 (기본값)            |AQE가 자동 조정                  |
|5GB 이상     |200 이상               |AQE `initialPartitionNum` 활용|


> **핵심:** AQE가 활성화되어 있으므로 `spark.sql.shuffle.partitions`를 넉넉하게 설정(예: 200)해도 AQE가 런타임에 불필요한 빈 파티션을 병합해준다. 너무 적게 잡는 것보다 넉넉하게 잡는 편이 안전하다.

### 3.3 Iceberg Write 관련 설정

현재 워크플로우가 avro → Iceberg append이므로 아래 Iceberg 쪽 설정도 확인이 필요하다.

|설정 (Iceberg 테이블 속성)           |기본값                         |설명                           |
|------------------------------|----------------------------|-----------------------------|
|`write.distribution-mode`     |hash (파티션 테이블) / none (비파티션)|쓰기 시 데이터 분배 모드. hash는 셔플을 유발함|
|`write.target-file-size-bytes`|512MB                       |Iceberg가 데이터 파일을 롤오버하는 목표 크기 |
|`write.format.default`        |parquet                     |Iceberg 테이블의 기본 저장 포맷        |

**고려사항:**

- `write.distribution-mode=none`으로 설정하면 셔플을 건너뛰어 쓰기 속도가 빨라지지만, 소규모 파일이 많이 생성될 수 있다. 이 경우 주기적 compaction이 필요하다.
- `write.distribution-mode=hash`(기본)는 파티션별로 데이터를 모아 쓰므로 파일 수가 적고 읽기 성능에 유리하지만, 셔플 비용이 추가된다.
- Iceberg 공식 문서에 따르면, Spark 태스크 크기가 `write.target-file-size-bytes`보다 작으면 해당 크기의 파일이 생성되지 않는다. 디스크에 쓰여지는 파일은 컬럼 형식 + 압축으로 인해 Spark의 인메모리 크기보다 훨씬 작아진다.

-----

## 4. 고정 Executor 수 vs Dynamic Allocation 비교 분석

### 4.1 비교표

|항목             |고정 Executor (현재 방식)|Dynamic Allocation                |
|---------------|-------------------|----------------------------------|
|**설정 복잡도**     |낮음 (공식으로 단순 계산)    |중간 (추가 설정 필요)                     |
|**리소스 효율**     |전체 Job 동안 고정 점유    |필요할 때만 할당/반환                      |
|**K8S 호환성**    |완전 지원              |지원됨 (셔플 트래킹 필요)                   |
|**예측 가능성**     |높음 (항상 동일 리소스)     |낮음 (런타임에 변동)                      |
|**스케일 업/다운**   |수동 (공식 수정 필요)      |자동                                |
|**클러스터 공유**    |비효율 (미사용 리소스 점유)   |효율적 (유휴 executor 반환)              |
|**셔플 데이터 안정성** |안정적 (executor 유지)  |주의 필요 (executor 반환 시 셔플 데이터 유실 가능)|
|**Pod 기동 오버헤드**|1회 (시작 시)          |N회 (동적 추가 시마다)                    |

### 4.2 현재 워크플로우에 대한 분석

**현재 워크플로우 특성:**

- 단방향 파이프라인: avro read → Iceberg append
- 배치 단위로 처리 (Airflow에서 트리거)
- 처리 대상 데이터 크기가 매 실행마다 다름
- Iceberg write 시 hash 분배 모드 사용 시 셔플 발생

**고정 Executor 방식이 적합한 경우:**

- 배치별 데이터 크기가 비교적 일정한 경우
- K8S 클러스터를 이 잡 전용으로 사용하는 경우
- Pod 기동 시간이 중요한 경우 (executor 추가 시 K8S Pod 생성에 시간 소요)
- 셔플 데이터의 안정성이 중요한 경우

**Dynamic Allocation이 적합한 경우:**

- 배치별 데이터 크기 편차가 큰 경우
- K8S 클러스터를 여러 잡이 공유하는 경우
- 리소스 비용 최적화가 중요한 경우

### 4.3 Dynamic Allocation K8S 설정 참고

K8S 환경에서 Dynamic Allocation을 사용하려면 아래 설정이 필요하다.

```properties
# Dynamic Allocation 활성화
spark.dynamicAllocation.enabled=true

# K8S에서는 External Shuffle Service 대신 Shuffle Tracking 사용
spark.dynamicAllocation.shuffleTracking.enabled=true

# Executor 수 범위
spark.dynamicAllocation.minExecutors=1
spark.dynamicAllocation.maxExecutors=20

# Executor 유휴 시 제거 타임아웃 (기본 60s)
spark.dynamicAllocation.executorIdleTimeout=60s

# 셔플 데이터가 있는 executor의 제거 타임아웃
spark.dynamicAllocation.shuffleTracking.timeout=600s
```

> **주의 (Spark on K8S 공식 문서):** K8S에서 Dynamic Allocation 사용 시 External Shuffle Service가 지원되지 않으므로 `spark.dynamicAllocation.shuffleTracking.enabled=true`가 필수이다. 셔플 데이터가 있는 executor는 셔플 트래킹 타임아웃이 만료될 때까지 제거되지 않으므로, 최악의 경우 이전 스테이지의 executor가 계속 유지되어 클러스터 리소스를 더 많이 점유할 수 있다.

### 4.4 권장 사항

**현재 상황에서는 고정 Executor 방식을 유지하되, 산정 기준을 개선하는 것을 권장한다.**

이유:

1. 현재 워크플로우가 단순 read → append로, 스테이지별 리소스 요구량 차이가 크지 않아 Dynamic Allocation의 이점이 제한적이다.
1. K8S 환경에서 Dynamic Allocation은 셔플 트래킹에 의존하는데, executor가 반환된 후 셔플 데이터를 재계산해야 하는 상황이 발생할 수 있다.
1. 배치별 데이터 크기가 달라지는 문제는 현재 공식(`총 크기 / 70MB + 1`)이 이미 동적으로 대응하고 있다.
1. Pod 기동 오버헤드가 없어 처리 시간 예측이 용이하다.

**다만, 아래 상황이라면 Dynamic Allocation 전환을 검토:**

- 클러스터를 여러 팀/잡이 공유하여 리소스 경합이 빈번한 경우
- 배치 데이터 크기 편차가 매우 커서(예: 10MB ~ 10GB) 고정 방식의 낭비가 심한 경우
- 비용 최적화가 최우선 과제인 경우

-----

## 5. 튜닝 프로세스 가이드

### 5.1 단계별 접근

#### Step 1: 기본 설정으로 시작

```bash
--driver-cores 1
--driver-memory 2g
--executor-cores 2
--executor-memory 2g
--num-executors <avro 총 크기 / 70MB + 1>
--conf spark.sql.shuffle.partitions=200
--conf spark.sql.adaptive.enabled=true
--conf spark.sql.adaptive.coalescePartitions.enabled=true
--conf spark.sql.adaptive.coalescePartitions.parallelismFirst=true
```

#### Step 2: Spark UI로 모니터링

아래 항목들을 Spark UI에서 확인한다:

|확인 항목 |위치                           |정상 기준                   |
|------|-----------------------------|------------------------|
|태스크 분포|Stages 탭 → Task Metrics      |태스크간 처리 시간 편차가 적을수록 좋음  |
|GC 시간 |Executors 탭 → GC Time        |전체 실행 시간의 10% 미만        |
|셔플 데이터|Stages 탭 → Shuffle Read/Write|비정상적으로 큰 셔플 확인          |
|파티션 수 |SQL 탭 → Exchange 노드          |AQE가 적절히 병합했는지 확인       |
|메모리 사용|Executors 탭 → Memory Used    |Peak memory가 할당량의 70% 이하|

#### Step 3: 병목 지점별 튜닝

|증상                      |원인 추정                       |조치                                    |
|------------------------|----------------------------|--------------------------------------|
|GC 시간이 전체의 10% 초과       |executor-memory 부족          |executor-memory 증가 (2g → 4g)          |
|태스크 처리 시간 편차가 큼         |데이터 스큐                      |repartition 또는 AQE skew join 확인       |
|셔플 write가 비정상적으로 큼      |write.distribution-mode=hash|none으로 변경 고려 (+ 추후 compaction)        |
|전체 잡 시간이 길지만 CPU 사용률 낮음 |executor 수 부족               |num-executors 증가                      |
|executor OOMKilled (K8S)|memoryOverhead 부족           |`spark.executor.memoryOverhead` 명시적 설정|

#### Step 4: 벤치마크 및 기록

각 설정 변경 시 아래 항목을 기록하여 비교한다:

```
| 테스트 ID | 날짜 | 데이터 크기 | num-executors | executor-cores | executor-memory | 처리 시간 | 비고 |
```

-----

## 6. 종합 권장 설정

### 6.1 기본 설정 (소규모 배치: ~ 1GB)

```bash
--driver-cores 1
--driver-memory 2g
--executor-cores 2
--executor-memory 2g
--num-executors <avro 총 크기 / 70MB + 1>
--conf spark.sql.shuffle.partitions=200
--conf spark.sql.adaptive.enabled=true
--conf spark.sql.adaptive.coalescePartitions.enabled=true
--conf spark.sql.adaptive.coalescePartitions.parallelismFirst=true
```

### 6.2 중규모 배치 (1GB ~ 5GB)

```bash
--driver-cores 1
--driver-memory 2g
--executor-cores 4
--executor-memory 4g
--num-executors <avro 총 크기 / 70MB + 1>
--conf spark.sql.shuffle.partitions=200
--conf spark.sql.adaptive.enabled=true
--conf spark.sql.adaptive.coalescePartitions.enabled=true
--conf spark.sql.adaptive.coalescePartitions.parallelismFirst=true
```

### 6.3 추가 권장 설정 (공통)

```properties
# S3(MinIO) 대상 디렉토리 리스팅 병렬화
spark.sql.sources.parallelPartitionDiscovery.parallelism=20

# Iceberg write 최적화 (필요시)
# write.distribution-mode=none  → 셔플 제거, 쓰기 속도 우선 시
# write.distribution-mode=hash  → 파일 수 최소화, 읽기 성능 우선 시 (기본값)
```

-----

## 7. TODO / 개선 과제

|과제                         |우선순위|설명                                                |
|---------------------------|----|--------------------------------------------------|
|num-executors 산정 기준 검증     |높음  |70MB 기준을 `maxPartitionBytes(128MB)` 기반 공식과 비교 벤치마크|
|executor-memory 최적값 측정     |높음  |Spark UI에서 peak memory를 확인하여 현재 메모리 대비 실제 사용량 분석  |
|shuffle.partitions 검증      |중간  |AQE 활성화 상태에서 70 vs 200 비교                         |
|write.distribution-mode 테스트|중간  |none vs hash 모드의 쓰기 성능, 파일 수, 후속 읽기 성능 비교         |
|Dynamic Allocation 파일럿     |낮음  |클러스터 공유 이슈 발생 시 검토                                |
|모니터링 대시보드 구축               |중간  |잡별 실행 시간, 리소스 사용량 추적                              |

-----

## 참고 문서

- [Spark 4.1.1 Tuning Guide](https://spark.apache.org/docs/latest/tuning.html)
- [Spark 4.1.1 SQL Performance Tuning](https://spark.apache.org/docs/latest/sql-performance-tuning.html)
- [Spark on Kubernetes](https://spark.apache.org/docs/latest/running-on-kubernetes.html)
- [Spark 4.1.1 Configuration](https://spark.apache.org/docs/latest/configuration.html)
- [Iceberg 1.10.0 Spark Writes](https://iceberg.apache.org/docs/1.10.0/spark-writes/)
- [Iceberg Spark Configuration](https://iceberg.apache.org/docs/latest/spark-configuration/)