__all__ = ['CronJobRun']


import sqlalchemy as sa

from .base import Base


class CronJobRun(Base):
    """A record of a run (or attempted run) of a cron job."""

    script = sa.Column(
        sa.String,
        nullable=False,
        doc="Name of script being run.",
    )
    exit_status = sa.Column(
        sa.Integer,
        nullable=True,
        doc="Exit status of cron job subprocess (e.g. 0 or 1).",
    )
    output = sa.Column(
        sa.String,
        doc="Cron job's subprocess output, or exception string.",
    )
