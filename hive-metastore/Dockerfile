# Hive Metastore standalone 이미지
# - apache/hive 3.1.3 기반 (Hive 4.x는 Iceberg 미지원)
# - PostgreSQL JDBC 드라이버 추가
FROM apache/hive:3.1.3

USER root

# PostgreSQL JDBC 드라이버 추가
ADD https://jdbc.postgresql.org/download/postgresql-42.7.4.jar /opt/hive/lib/postgresql-42.7.4.jar
RUN chmod 644 /opt/hive/lib/postgresql-42.7.4.jar

USER hive
