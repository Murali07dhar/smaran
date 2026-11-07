"""initial schema: all 16 SMARAN tables (see app/models.py)

Revision ID: 0001
Revises: none
Create Date: 2026-10-22 02:40:36.586734
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('sync_ops',
    sa.Column('op_id', sa.Uuid(), nullable=False),
    sa.Column('device_id', sa.String(length=64), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('op_id', name=op.f('pk_sync_ops'))
    )
    op.create_index('ix_sync_ops_applied_at', 'sync_ops', ['applied_at'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('pin_hash', sa.String(length=255), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("role IN ('patient', 'caregiver', 'health_worker', 'admin')", name=op.f('ck_users_role')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('phone', name=op.f('uq_users_phone'))
    )
    op.create_table('alerts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('severity', sa.String(length=8), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('acknowledged_by', sa.Uuid(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.CheckConstraint("kind IN ('score_drop', 'activity_drop', 'missed_reminders', 'severity')", name=op.f('ck_alerts_kind')),
    sa.CheckConstraint("severity IN ('info', 'watch', 'alert')", name=op.f('ck_alerts_severity')),
    sa.ForeignKeyConstraint(['acknowledged_by'], ['users.id'], name=op.f('fk_alerts_acknowledged_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_alerts_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts'))
    )
    op.create_index('ix_alerts_open_patient', 'alerts', ['patient_id'], unique=False, postgresql_where=sa.text('acknowledged_at IS NULL'), sqlite_where=sa.text('acknowledged_at IS NULL'))
    op.create_index('ix_alerts_patient_created', 'alerts', ['patient_id', 'created_at'], unique=False)
    op.create_table('caregiver_links',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('caregiver_id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('relation', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['caregiver_id'], ['users.id'], name=op.f('fk_caregiver_links_caregiver_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_caregiver_links_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_caregiver_links')),
    sa.UniqueConstraint('caregiver_id', 'patient_id', name='uq_caregiver_links_caregiver_patient')
    )
    op.create_index('ix_caregiver_links_patient_id', 'caregiver_links', ['patient_id'], unique=False)
    op.create_table('consent_records',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('granted', sa.Boolean(), nullable=False),
    sa.Column('granted_by', sa.Uuid(), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("kind IN ('camera', 'mic', 'data_sharing')", name=op.f('ck_consent_records_kind')),
    sa.ForeignKeyConstraint(['granted_by'], ['users.id'], name=op.f('fk_consent_records_granted_by_users')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_consent_records_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_consent_records'))
    )
    op.create_index('ix_consent_records_patient_kind_ts', 'consent_records', ['patient_id', 'kind', 'ts'], unique=False)
    op.create_table('game_sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('game_id', sa.String(length=64), nullable=False),
    sa.Column('domain', sa.String(length=16), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('difficulty', sa.Integer(), nullable=False),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('device_id', sa.String(length=64), nullable=False),
    sa.Column('server_ts', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("domain IN ('memory', 'attention', 'routine', 'pattern_object', 'executive')", name=op.f('ck_game_sessions_domain')),
    sa.CheckConstraint('difficulty >= 1 AND difficulty <= 10', name=op.f('ck_game_sessions_difficulty_range')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_game_sessions_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_game_sessions'))
    )
    op.create_index('ix_game_sessions_patient_started', 'game_sessions', ['patient_id', 'started_at'], unique=False)
    op.create_table('media_assets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('uploader_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('mime', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('enc_path', sa.String(length=512), nullable=False),
    sa.Column('nonce', sa.LargeBinary(), nullable=False),
    sa.Column('tags', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("kind IN ('photo', 'audio')", name=op.f('ck_media_assets_kind')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_media_assets_patient_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploader_id'], ['users.id'], name=op.f('fk_media_assets_uploader_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media_assets'))
    )
    op.create_index('ix_media_assets_patient_created', 'media_assets', ['patient_id', 'created_at'], unique=False)
    op.create_table('memory_triggers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('cue_id', sa.String(length=64), nullable=False),
    sa.Column('cue_type', sa.String(length=32), nullable=False),
    sa.Column('valence_label', sa.String(length=16), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('last_validated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('half_life_days', sa.Float(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("valence_label IN ('joy', 'comfort', 'excitement', 'amusement', 'familiarity', 'neutral', 'negative')", name=op.f('ck_memory_triggers_valence_label')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_memory_triggers_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_memory_triggers')),
    sa.UniqueConstraint('patient_id', 'cue_id', name='uq_memory_triggers_patient_cue')
    )
    op.create_table('patient_profiles',
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('age', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('estimated_stage', sa.String(length=32), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.CheckConstraint('age >= 0 AND age <= 130', name=op.f('ck_patient_profiles_age_range')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_patient_profiles_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('patient_id', name=op.f('pk_patient_profiles'))
    )
    op.create_table('reminders',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('schedule_rrule', sa.String(length=500), nullable=False),
    sa.Column('locale', sa.String(length=8), nullable=False),
    sa.Column('voice_clip_id', sa.String(length=64), nullable=True),
    sa.Column('escalate_after_misses', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('server_version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("category IN ('medicine', 'hydration', 'activity', 'appointment')", name=op.f('ck_reminders_category')),
    sa.CheckConstraint('escalate_after_misses >= 0', name=op.f('ck_reminders_escalate_nonneg')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_reminders_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reminders'))
    )
    op.create_index('ix_reminders_patient_active', 'reminders', ['patient_id', 'active'], unique=False)
    op.create_table('routines',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('steps', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('server_version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_routines_created_by_users')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_routines_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_routines'))
    )
    op.create_index('ix_routines_patient_id', 'routines', ['patient_id'], unique=False)
    op.create_table('severity_indicators',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('band', sa.String(length=16), nullable=False),
    sa.Column('gds_style_indicator', sa.Integer(), nullable=False),
    sa.Column('drivers', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('gds_style_indicator >= 1 AND gds_style_indicator <= 7', name=op.f('ck_severity_indicators_gds_range')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_severity_indicators_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_severity_indicators'))
    )
    op.create_index('ix_severity_indicators_patient_computed', 'severity_indicators', ['patient_id', 'computed_at'], unique=False)
    op.create_table('sync_changes',
    sa.Column('cursor', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('entity', sa.String(length=32), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(length=8), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('server_ts', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("action IN ('upsert', 'delete')", name=op.f('ck_sync_changes_action')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_sync_changes_patient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('cursor', name=op.f('pk_sync_changes'))
    )
    op.create_index('ix_sync_changes_patient_cursor', 'sync_changes', ['patient_id', 'cursor'], unique=False)
    op.create_table('emotion_samples',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=True),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('valence', sa.Float(), nullable=False),
    sa.Column('arousal', sa.Float(), nullable=False),
    sa.Column('label', sa.String(length=16), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('source', sa.String(length=8), nullable=False),
    sa.Column('caregiver_confirmed', sa.Boolean(), nullable=True),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("label IN ('joy', 'comfort', 'excitement', 'amusement', 'familiarity', 'neutral', 'negative')", name=op.f('ck_emotion_samples_label')),
    sa.CheckConstraint("source IN ('face', 'speech', 'fused')", name=op.f('ck_emotion_samples_source')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_emotion_samples_patient_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_id'], ['game_sessions.id'], name=op.f('fk_emotion_samples_session_id_game_sessions'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_emotion_samples'))
    )
    op.create_index('ix_emotion_samples_patient_ts', 'emotion_samples', ['patient_id', 'ts'], unique=False)
    op.create_index('ix_emotion_samples_session_id', 'emotion_samples', ['session_id'], unique=False)
    op.create_table('game_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('item_id', sa.String(length=64), nullable=False),
    sa.Column('correct', sa.Boolean(), nullable=True),
    sa.Column('response_ms', sa.Integer(), nullable=True),
    sa.Column('cue_id', sa.String(length=64), nullable=True),
    sa.Column('with_cue', sa.Boolean(), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_game_events_patient_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_id'], ['game_sessions.id'], name=op.f('fk_game_events_session_id_game_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_game_events'))
    )
    op.create_index('ix_game_events_patient_ts', 'game_events', ['patient_id', 'ts'], unique=False)
    op.create_index('ix_game_events_session_ts', 'game_events', ['session_id', 'ts'], unique=False)
    op.create_table('reminder_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('reminder_id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=8), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('done', 'later', 'missed')", name=op.f('ck_reminder_events_status')),
    sa.ForeignKeyConstraint(['patient_id'], ['users.id'], name=op.f('fk_reminder_events_patient_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reminder_id'], ['reminders.id'], name=op.f('fk_reminder_events_reminder_id_reminders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reminder_events'))
    )
    op.create_index('ix_reminder_events_patient_due', 'reminder_events', ['patient_id', 'due_at'], unique=False)
    op.create_index('ix_reminder_events_reminder_due', 'reminder_events', ['reminder_id', 'due_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_reminder_events_reminder_due', table_name='reminder_events')
    op.drop_index('ix_reminder_events_patient_due', table_name='reminder_events')
    op.drop_table('reminder_events')
    op.drop_index('ix_game_events_session_ts', table_name='game_events')
    op.drop_index('ix_game_events_patient_ts', table_name='game_events')
    op.drop_table('game_events')
    op.drop_index('ix_emotion_samples_session_id', table_name='emotion_samples')
    op.drop_index('ix_emotion_samples_patient_ts', table_name='emotion_samples')
    op.drop_table('emotion_samples')
    op.drop_index('ix_sync_changes_patient_cursor', table_name='sync_changes')
    op.drop_table('sync_changes')
    op.drop_index('ix_severity_indicators_patient_computed', table_name='severity_indicators')
    op.drop_table('severity_indicators')
    op.drop_index('ix_routines_patient_id', table_name='routines')
    op.drop_table('routines')
    op.drop_index('ix_reminders_patient_active', table_name='reminders')
    op.drop_table('reminders')
    op.drop_table('patient_profiles')
    op.drop_table('memory_triggers')
    op.drop_index('ix_media_assets_patient_created', table_name='media_assets')
    op.drop_table('media_assets')
    op.drop_index('ix_game_sessions_patient_started', table_name='game_sessions')
    op.drop_table('game_sessions')
    op.drop_index('ix_consent_records_patient_kind_ts', table_name='consent_records')
    op.drop_table('consent_records')
    op.drop_index('ix_caregiver_links_patient_id', table_name='caregiver_links')
    op.drop_table('caregiver_links')
    op.drop_index('ix_alerts_patient_created', table_name='alerts')
    op.drop_index('ix_alerts_open_patient', table_name='alerts', postgresql_where=sa.text('acknowledged_at IS NULL'), sqlite_where=sa.text('acknowledged_at IS NULL'))
    op.drop_table('alerts')
    op.drop_table('users')
    op.drop_index('ix_sync_ops_applied_at', table_name='sync_ops')
    op.drop_table('sync_ops')
