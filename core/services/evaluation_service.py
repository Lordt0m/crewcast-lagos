import logging
from django.db import transaction
from core.models import Job, ForecastSnapshot, Recommendation, Site
from core.evaluator import evaluate_forecast, EvaluationResult

logger = logging.getLogger(__name__)


def evaluate_and_record_job(job: Job, snapshot: ForecastSnapshot) -> tuple[Recommendation, bool]:
    """
    Evaluates a single Job against a ForecastSnapshot using the pure evaluator
    and persists the recommendation. Uniquely identified by (job, revision, policy_version, snapshot).
    """
    thresholds = job.policy_version.get_thresholds_dict()
    eval_result: EvaluationResult = evaluate_forecast(
        job_start_utc=job.start_time,
        job_end_utc=job.end_time,
        policy_thresholds=thresholds,
        hourly_data=snapshot.hourly_data,
    )

    with transaction.atomic():
        recommendation, created = Recommendation.objects.get_or_create(
            job=job,
            job_revision=job.revision,
            policy_version=job.policy_version,
            snapshot=snapshot,
            defaults={
                'status': eval_result.status,
                'reasons': eval_result.reasons,
                'metrics_summary': eval_result.max_metrics,
                'evaluated_hours': eval_result.evaluated_hours_wat,
            }
        )

    if created:
        logger.info(
            f"Created recommendation: Job {job.pk} ('{job.title}') status={eval_result.status} "
            f"(rev {job.revision}, snapshot {snapshot.content_hash[:8]})"
        )
    return recommendation, created


def evaluate_all_jobs_for_site(site: Site, snapshot: ForecastSnapshot) -> list[Recommendation]:
    """Evaluates all active jobs for a site against the given snapshot."""
    recommendations = []
    jobs = Job.objects.filter(site=site)
    for job in jobs:
        rec, _ = evaluate_and_record_job(job, snapshot)
        recommendations.append(rec)
    return recommendations


def reevaluate_job_with_latest_snapshot(job: Job) -> Recommendation | None:
    """Finds the latest snapshot for the job's site and evaluates."""
    latest_snapshot = ForecastSnapshot.objects.filter(site=job.site).order_by('-first_retrieved_at').first()
    if latest_snapshot:
        rec, _ = evaluate_and_record_job(job, latest_snapshot)
        return rec
    return None
