from django.db import migrations, models

def assign_session(apps, schema_editor):
    FocusData     = apps.get_model('focus', 'FocusData')
    StudySession  = apps.get_model('focus', 'StudySession')

    # timestamp 시점에 활성 세션(end_at is not null)이었던 세션 찾기
    for fd in FocusData.objects.filter(session__isnull=True):
        sess = (
            StudySession.objects
            .filter(user=fd.user,
                    start_at__lte=fd.timestamp,
                    end_at__isnull=False,
                    end_at__gte=fd.timestamp)
            .order_by('-start_at')
            .first()
        )
        if sess:
            fd.session = sess
            fd.save()

class Migration(migrations.Migration):

    dependencies = [
        ('focus', '0005_studysession_success_score'),
    ]

    operations = [
        migrations.RunPython(assign_session, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='focusdata',
            name='session',
            field=migrations.swappable_dependency('focus.StudySession') and  # adjust if you use swappable AUTH_USER_MODEL
                   models.ForeignKey(
                       to='focus.StudySession',
                       on_delete=models.CASCADE,
                   ),
        ),
    ]
