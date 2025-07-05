# 알림관련
# import os
# from celery import Celery
#
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
#
# app = Celery('config')
# # Django settings 하위 CELERY_* 설정을 모두 가져옴
# app.config_from_object('django.conf:settings', namespace='CELERY')
# app.autodiscover_tasks()