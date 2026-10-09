"""Initial project, immutable paper import, search and encrypted settings schema."""
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False))
    op.create_table("papers",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("canonical_id", sa.String(500), nullable=False),
        sa.Column("doi", sa.String(300)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False))
    op.create_index("ix_papers_canonical_id", "papers", ["canonical_id"])
    op.create_index("ix_papers_doi", "papers", ["doi"])
    op.create_table("project_papers",
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("paper_id", sa.String(80), sa.ForeignKey("papers.id"), primary_key=True),
        sa.Column("linked_at", sa.String(64), nullable=False))
    op.create_table("saved_searches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("queries", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False))
    op.create_index("ix_saved_searches_project_id", "saved_searches", ["project_id"])
    op.create_table("settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("encrypted_value", sa.Text(), nullable=False))
def downgrade():
    op.drop_table("settings")
    op.drop_table("saved_searches")
    op.drop_table("project_papers")
    op.drop_table("papers")
    op.drop_table("projects")
