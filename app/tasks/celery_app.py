"""Celery 应用实例配置。

队列划分（见 AGENTS.md 第 6 节）：
- alerts      实时告警（低延迟）
- analysis    分析计算（CPU 密集）
- reports     报表生成
- maintenance 系统维护
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "shm",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.alert_tasks",
        "app.tasks.analysis_tasks",
        "app.tasks.report_tasks",
        "app.tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_default_queue="maintenance",
    task_routes={
        "app.tasks.alert_tasks.*": {"queue": "alerts"},
        "app.tasks.analysis_tasks.*": {"queue": "analysis"},
        "app.tasks.report_tasks.*": {"queue": "reports"},
        "app.tasks.maintenance_tasks.*": {"queue": "maintenance"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
