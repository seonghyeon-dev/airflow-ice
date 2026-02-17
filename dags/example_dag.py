"""
동작 확인용 샘플 DAG.

BashOperator를 사용하여 간단한 hello world 메시지를 출력합니다.
"""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="example_hello_world",
    description="동작 확인용 샘플 DAG",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example"],
) as dag:

    hello_task = BashOperator(
        task_id="say_hello",
        bash_command='echo "Hello from Airflow!"',
    )

    date_task = BashOperator(
        task_id="print_date",
        bash_command="date",
    )

    hello_task >> date_task
