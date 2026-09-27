"""src/infrastructure/jobs/scheduler.py — Scheduler APScheduler para jobs."""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


class SchedulerTI:
    """Orchestrator de jobs periódicos."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()

    def schedule_job_diagnostico_semanal(self, job_func, interval_hours: int = 168):
        """Agenda job de diagnóstico cada 7 días (168 horas)."""
        self.scheduler.add_job(
            job_func,
            trigger=IntervalTrigger(hours=interval_hours),
            id="job_diagnostico_semanal",
            name="Diagnóstico TI semanal",
            replace_existing=True,
        )

    def start(self):
        """Inicia el scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()

    def stop(self):
        """Detiene el scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
