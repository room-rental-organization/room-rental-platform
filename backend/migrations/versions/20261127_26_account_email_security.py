"""Email verification, single-use recovery links and session revocation."""
from alembic import op
import sqlalchemy as sa

revision = '20261127_26'
down_revision = '20261124_25'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing accounts retain access, without falsely marking their emails verified.
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('email_verification_required', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('auth_version', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('account_tokens',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('purpose', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("purpose IN ('verify_email', 'reset_password')", name='account_tokens_purpose_check'))
    op.create_index('account_tokens_user_purpose_created_idx', 'account_tokens', ['user_id', 'purpose', 'created_at'])


def downgrade() -> None:
    op.drop_table('account_tokens')
    op.drop_column('users', 'auth_version')
    op.drop_column('users', 'email_verification_required')
    op.drop_column('users', 'email_verified_at')
