from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_mpesa_attempt'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='generation_key',
            field=models.CharField(blank=True, default='', max_length=160),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.UniqueConstraint(
                condition=~models.Q(generation_key=''),
                fields=('organization', 'generation_key'),
                name='unique_invoice_generation_key_per_org',
            ),
        ),
    ]
