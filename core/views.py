import json
from functools import wraps
from datetime import datetime, date, timedelta, timezone as dt_timezone
from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import connection
from django.core.cache import cache
from django.utils import timezone

from .models import (
    Site,
    Job,
    WeatherPolicyVersion,
    ForecastSnapshot,
    Recommendation,
    BudgetWindow,
    SyncAttempt,
    ProviderCircuitState,
    ScheduledForecastRun,
    LAGOS_TZ,
)
from .forms import JobForm, SiteForm, WeatherPolicyForm
from .tasks import WORKER_HEARTBEAT_CACHE_KEY, SCHEDULER_HEARTBEAT_CACHE_KEY
from .services.freshness import get_freshness_state, get_effective_planning_display
from .evaluator import get_intersecting_hour_instants
from .services.evaluation_service import evaluate_and_record_job
from .services.cache_service import get_board_cache_version, invalidate_board_cache, BOARD_CACHE_TTL_SECONDS
from .services.forecast_selection import latest_verified_success


def demo_mode_guard(view_func):
    """Prevents state-changing HTTP methods when DEMO_MODE is True."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(settings, 'DEMO_MODE', False) and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                return JsonResponse({'error': 'State-changing actions are disabled in Demo Mode.'}, status=403)
            messages.warning(request, "State-changing actions are disabled in Demo Mode.")
            return HttpResponseForbidden("State-changing actions are disabled in Demo Mode.")
        return view_func(request, *args, **kwargs)
    return _wrapped


def format_duration_ago(seconds: float) -> str:
    """Formats seconds into human readable '2h 10m ago'."""
    if seconds == float('inf'):
        return "Never retrieved"
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m"
    else:
        return "<1m"


def scheduled_forecast_status(now=None):
    """Report the latest scheduled invocation from durable database state."""
    now = now or timezone.now()
    run = ScheduledForecastRun.objects.first()
    if run is None:
        return {'status': 'inactive', 'last_seen': None, 'age_display': 'Never seen', 'attempt_count': 0}
    age_seconds = max(0.0, (now - run.started_at).total_seconds())
    if run.status == ScheduledForecastRun.Status.FAILED:
        status = 'failed'
    elif run.status == ScheduledForecastRun.Status.RUNNING:
        status = 'running' if age_seconds <= 600 else 'stale'
    else:
        status = 'ok' if age_seconds <= 7200 else 'stale'
    return {
        'status': status,
        'last_seen': run.started_at.astimezone(LAGOS_TZ).strftime('%d %b %H:%M WAT'),
        'started_at': run.started_at.isoformat(),
        'age_seconds': round(age_seconds, 1),
        'age_display': format_duration_ago(age_seconds),
        'attempt_count': run.attempt_count,
    }


def job_board_view(request):
    """
    Main job board displaying scheduled jobs grouped by planning status:
    1. No current recommendation (Pending / Expired)
    2. Unsuitable
    3. Caution
    4. Suitable
    Zero live calls to Open-Meteo are ever made from this request.
    Caches the board payload without caching displayed age:
    displayed age is computed at render time so cache hits advance age naturally.
    """
    now = timezone.now()
    now_lagos = now.astimezone(LAGOS_TZ)
    today_lagos = now_lagos.date()

    # 1. Selected date parsing & clamping
    date_param = request.GET.get('date')
    selected_date = today_lagos
    if date_param:
        try:
            parsed_d = date.fromisoformat(date_param)
            if today_lagos <= parsed_d <= today_lagos + timedelta(days=6):
                selected_date = parsed_d
        except ValueError:
            pass

    selected_date_str = selected_date.isoformat()
    selected_date_display = selected_date.strftime('%A, %d %B %Y')

    # 2. Cache query for heavy job and recommendation data
    cache_version = get_board_cache_version()
    cache_key = f"crewcast:board:payload:retrieval:v{cache_version}:{selected_date_str}"
    cached_payload = None
    cache_hit = False

    try:
        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            cache_hit = True
    except Exception as exc:
        cached_payload = None

    if cached_payload is None:
        # Build 7-day planning horizon counts
        horizon_days = []
        for i in range(7):
            day_date = today_lagos + timedelta(days=i)
            day_start = datetime(day_date.year, day_date.month, day_date.day, 0, 0, tzinfo=LAGOS_TZ).astimezone(dt_timezone.utc)
            day_end = day_start + timedelta(days=1)
            count = Job.objects.filter(
                site__is_active=True,
                start_time__lt=day_end,
                end_time__gt=day_start
            ).count()

            horizon_days.append({
                'date_str': day_date.isoformat(),
                'weekday': day_date.strftime('%a'),
                'day_num': day_date.strftime('%d'),
                'month': day_date.strftime('%b'),
                'job_count': count,
            })

        # Query jobs overlapping selected date
        sel_start_utc = datetime(selected_date.year, selected_date.month, selected_date.day, 0, 0, tzinfo=LAGOS_TZ).astimezone(dt_timezone.utc)
        sel_end_utc = sel_start_utc + timedelta(days=1)

        jobs = Job.objects.filter(
            site__is_active=True,
            start_time__lt=sel_end_utc,
            end_time__gt=sel_start_utc
        ).select_related('site', 'policy_version').order_by('start_time', 'title')

        jobs_data = []
        current_attempts = {}
        for job in jobs:
            site = job.site
            if site.pk not in current_attempts:
                current_attempts[site.pk] = latest_verified_success(site)
            current_attempt = current_attempts[site.pk]
            latest_rec = Recommendation.objects.filter(
                job=job,
                job_revision=job.revision,
                policy_version=job.policy_version,
                snapshot_id=current_attempt.snapshot_id if current_attempt else None,
            ).order_by('-evaluated_at').first()

            primary_reason = ""
            if latest_rec and latest_rec.reasons:
                primary_reason = latest_rec.reasons[0].get('message', '')

            jobs_data.append({
                'job_id': job.pk,
                'title': job.title,
                'site_name': site.name,
                'start_iso': job.start_time.isoformat(),
                'end_iso': job.end_time.isoformat(),
                'last_sync_iso': current_attempt.completed_at.isoformat() if current_attempt and current_attempt.completed_at else None,
                'rec_status': latest_rec.status if latest_rec else None,
                'primary_reason': primary_reason,
            })

        most_recent_sync = SyncAttempt.objects.filter(
            site__is_active=True,
            source_kind='worker',
            outcome='success',
            snapshot__source_kind='provider',
        ).order_by('-completed_at', '-pk').values_list('completed_at', flat=True).first()

        cached_payload = {
            'horizon_days': horizon_days,
            'jobs_data': jobs_data,
            'most_recent_sync_iso': most_recent_sync.isoformat() if most_recent_sync else None,
            'total_jobs_count': len(jobs_data),
        }
        try:
            cache.set(cache_key, cached_payload, timeout=BOARD_CACHE_TTL_SECONDS)
        except Exception:
            pass

    # 3. Dynamic render-time assembly: compute true advancing age from stored timestamps
    unactionable_jobs = []
    unsuitable_jobs = []
    caution_jobs = []
    suitable_jobs = []

    for item in cached_payload['jobs_data']:
        last_sync = datetime.fromisoformat(item['last_sync_iso']) if item['last_sync_iso'] else None
        freshness_state, age_seconds = get_freshness_state(last_sync, now=now)
        if last_sync is None:
            freshness_state = 'pending'

        display = get_effective_planning_display(item['rec_status'], freshness_state)

        start_dt = datetime.fromisoformat(item['start_iso'])
        end_dt = datetime.fromisoformat(item['end_iso'])
        start_lagos = start_dt.astimezone(LAGOS_TZ)
        end_lagos = end_dt.astimezone(LAGOS_TZ)
        time_window = f"{start_lagos.strftime('%H:%M')} – {end_lagos.strftime('%H:%M WAT')}"

        retrieval_age_text = (
            f"Forecast retrieved {format_duration_ago(age_seconds)} ago"
            if last_sync else "Waiting for first sync"
        )

        job_item = {
            'job': {
                'pk': item['job_id'],
                'title': item['title'],
                'site': {'name': item['site_name']},
            },
            'time_window_display': time_window,
            'start_iso': item['start_iso'],
            'display': display,
            'primary_reason': item['primary_reason'],
            'retrieval_age_display': retrieval_age_text,
        }

        status_key = display.get('actionable_status')
        if status_key == 'unsuitable':
            unsuitable_jobs.append(job_item)
        elif status_key == 'caution':
            caution_jobs.append(job_item)
        elif status_key == 'suitable':
            suitable_jobs.append(job_item)
        else:
            unactionable_jobs.append(job_item)

    most_recent_sync = datetime.fromisoformat(cached_payload['most_recent_sync_iso']) if cached_payload['most_recent_sync_iso'] else None
    b_state, b_age = get_freshness_state(most_recent_sync, now=now)
    if most_recent_sync is None:
        b_state = 'pending'

    board_freshness = {
        'state': b_state,
        'age_display': format_duration_ago(b_age),
    }

    context = {
        'horizon_days': cached_payload['horizon_days'],
        'selected_date_str': selected_date_str,
        'selected_date_display': selected_date_display,
        'board_freshness': board_freshness,
        'total_jobs_count': cached_payload['total_jobs_count'],
        'unactionable_jobs': unactionable_jobs,
        'unsuitable_jobs': unsuitable_jobs,
        'caution_jobs': caution_jobs,
        'suitable_jobs': suitable_jobs,
    }
    response = render(request, 'core/job_board.html', context)
    response['X-CrewCast-Cache'] = 'HIT' if cache_hit else 'MISS'
    return response


def job_detail_view(request, pk):
    """
    Detailed inspection of a planned job window:
    - Current recommendation and reasons
    - Evaluated hourly conditions
    - Historical recommendation comparison
    - Weather policy thresholds
    Zero live calls to Open-Meteo.
    """
    now = timezone.now()
    job = get_object_or_404(Job.objects.select_related('site', 'policy_version'), pk=pk)
    site = job.site

    current_attempt = latest_verified_success(site)
    latest_snapshot = current_attempt.snapshot if current_attempt else None
    verified_sync_at = current_attempt.completed_at if current_attempt else None

    # Freshness
    freshness_state, age_seconds = get_freshness_state(verified_sync_at, now=now)
    if verified_sync_at is None:
        freshness_state = 'pending'

    # Current recommendation
    current_rec = Recommendation.objects.filter(
        job=job,
        job_revision=job.revision,
        policy_version=job.policy_version,
        snapshot=latest_snapshot,
    ).order_by('-evaluated_at').first()

    effective_display = get_effective_planning_display(current_rec.status if current_rec else None, freshness_state)

    # Intersecting hourly conditions table
    hourly_evaluations = []
    if latest_snapshot and latest_snapshot.hourly_data:
        instants = get_intersecting_hour_instants(job.start_time, job.end_time)
        for inst in instants:
            iso_key = inst.isoformat()
            matched = latest_snapshot.hourly_data.get(iso_key)
            if not matched:
                alt = iso_key.replace("+00:00", "Z")
                matched = latest_snapshot.hourly_data.get(alt)

            if matched:
                inst_lagos = inst.astimezone(LAGOS_TZ)
                label = f"{(inst_lagos - timedelta(hours=1)).strftime('%H:%M')}–{inst_lagos.strftime('%H:%M')}"
                hourly_evaluations.append({
                    'hour_label': label,
                    'prob': matched.get('precipitation_probability', '—'),
                    'precip': matched.get('precipitation', '—'),
                    'gusts': matched.get('wind_gusts_10m', '—'),
                    'temp': matched.get('apparent_temperature', '—'),
                })

    # Prior recommendations for comparison
    prior_recs = Recommendation.objects.filter(
        job=job, snapshot__source_kind='provider'
    ).select_related('policy_version', 'snapshot').order_by('-evaluated_at')[:10]

    start_lagos = job.start_time.astimezone(LAGOS_TZ)
    end_lagos = job.end_time.astimezone(LAGOS_TZ)
    time_window_display = f"{start_lagos.strftime('%A, %d %B %Y')} from {start_lagos.strftime('%H:%M')} to {end_lagos.strftime('%H:%M WAT')}"

    retrieval_age_text = (
        f"Forecast retrieved {format_duration_ago(age_seconds)} ago"
        if verified_sync_at else "Waiting for first sync"
    )

    context = {
        'job': job,
        'snapshot': latest_snapshot,
        'current_rec': current_rec,
        'effective_display': effective_display,
        'freshness_state': freshness_state,
        'retrieval_age_display': retrieval_age_text,
        'time_window_display': time_window_display,
        'hourly_evaluations': hourly_evaluations,
        'prior_recs': prior_recs,
    }
    return render(request, 'core/job_detail.html', context)


@login_required
@demo_mode_guard
def job_create_view(request):
    """Manager view to create a new planned outdoor job."""
    if request.method == 'POST':
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.policy_version = WeatherPolicyVersion.get_latest_default()
            job.save()

            # Attempt initial evaluation with latest stored snapshot if available
            current_attempt = latest_verified_success(job.site)
            latest_snap = current_attempt.snapshot if current_attempt else None
            if latest_snap:
                evaluate_and_record_job(job, latest_snap)

            invalidate_board_cache()
            messages.success(request, f"Job '{job.title}' created.")
            return redirect('job_board')
    else:
        form = JobForm()
    return render(request, 'core/job_form.html', {'form': form, 'title': 'Add job'})


@login_required
@demo_mode_guard
def job_edit_view(request, pk):
    """Manager view to edit an existing job."""
    job = get_object_or_404(Job, pk=pk)
    if request.method == 'POST':
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            job = form.save()
            current_attempt = latest_verified_success(job.site)
            latest_snap = current_attempt.snapshot if current_attempt else None
            if latest_snap:
                evaluate_and_record_job(job, latest_snap)

            invalidate_board_cache()
            messages.success(request, f"Job '{job.title}' updated to revision {job.revision}.")
            return redirect('job_detail', pk=job.pk)
    else:
        form = JobForm(instance=job)
    return render(request, 'core/job_form.html', {'form': form, 'job': job, 'title': f'Edit job: {job.title}'})


@login_required
@demo_mode_guard
def site_create_view(request):
    """Manager view to add an outdoor work site."""
    if request.method == 'POST':
        form = SiteForm(request.POST)
        if form.is_valid():
            site = form.save()
            invalidate_board_cache()
            messages.success(request, f"Site '{site.name}' created.")
            return redirect('job_board')
    else:
        form = SiteForm()
    return render(request, 'core/site_form.html', {'form': form, 'title': 'Add site'})


@login_required
@demo_mode_guard
def policy_edit_view(request):
    """Manager view to review or update default weather policy (creates a new version)."""
    current_policy = WeatherPolicyVersion.objects.first()
    if request.method == 'POST':
        form = WeatherPolicyForm(request.POST)
        if form.is_valid():
            new_policy = form.save()
            invalidate_board_cache()
            messages.success(request, f"New policy version {new_policy.pk} saved.")
            return redirect('job_board')
    else:
        form = WeatherPolicyForm(instance=current_policy)
    return render(request, 'core/policy_form.html', {'form': form, 'current_policy': current_policy})


def health_check_view(request):
    """
    Health check endpoint distinguishing:
    1. web process (ok)
    2. database connectivity (ok / error)
    3. cache / broker connectivity (ok / degraded)
    4. Celery worker heartbeat (ok / stale / inactive)
    5. Celery scheduler heartbeat (ok / stale / inactive)
    """
    components = {
        'web': {'status': 'ok'},
        'database': {'status': 'unknown'},
        'cache': {'status': 'unknown'},
    }
    if settings.FORECAST_RUNNER == 'github_actions':
        components['scheduled_forecast'] = {'status': 'unknown'}
    else:
        components['worker_heartbeat'] = {'status': 'unknown'}
        components['scheduler_heartbeat'] = {'status': 'unknown'}
    
    # 1. Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                components['database']['status'] = 'ok'
            else:
                components['database']['status'] = 'error'
                components['database']['error'] = 'Unexpected query result'
    except Exception as exc:
        components['database']['status'] = 'error'
        components['database']['error'] = str(exc)

    # 2. Cache / Broker check
    cache_accessible = False
    if not settings.REDIS_URL:
        components['cache'] = {
            'status': 'not_configured',
            'detail': 'Shared cache disabled; reads use PostgreSQL',
        }
    else:
        try:
            test_key = 'crewcast:health:ping'
            cache.set(test_key, 'pong', timeout=10)
            cached_val = cache.get(test_key)
            if cached_val == 'pong':
                components['cache']['status'] = 'ok'
                cache_accessible = True
            else:
                components['cache']['status'] = 'degraded'
                components['cache']['detail'] = 'Cache read mismatch'
        except Exception as exc:
            components['cache']['status'] = 'degraded'
            components['cache']['error'] = str(exc)

    if settings.FORECAST_RUNNER == 'github_actions':
        if components['database']['status'] == 'ok':
            components['scheduled_forecast'] = scheduled_forecast_status()
        is_healthy = components['web']['status'] == 'ok' and components['database']['status'] == 'ok'
        return JsonResponse({
            'status': 'ok' if is_healthy else 'unhealthy',
            'timestamp': timezone.now().isoformat(),
            'components': components,
        }, status=200 if is_healthy else 503)

    # 3. Worker heartbeat check
    if cache_accessible:
        try:
            last_hb = cache.get(WORKER_HEARTBEAT_CACHE_KEY)
            if last_hb:
                hb_time = datetime.fromisoformat(last_hb)
                age_seconds = (timezone.now() - hb_time).total_seconds()
                components['worker_heartbeat'] = {
                    'status': 'ok' if age_seconds <= 180 else 'stale',
                    'last_heartbeat': last_hb,
                    'age_seconds': round(age_seconds, 1),
                }
            else:
                components['worker_heartbeat'] = {
                    'status': 'inactive',
                    'detail': 'No worker heartbeat recorded yet',
                }
        except Exception as exc:
            components['worker_heartbeat'] = {
                'status': 'unknown',
                'error': str(exc),
            }
    else:
        components['worker_heartbeat'] = {
            'status': 'inactive',
            'detail': 'Cache unreachable; worker heartbeat cannot be retrieved',
        }

    # 4. Scheduler heartbeat check
    if cache_accessible:
        try:
            last_shb = cache.get(SCHEDULER_HEARTBEAT_CACHE_KEY)
            if last_shb:
                shb_time = datetime.fromisoformat(last_shb)
                s_age_seconds = (timezone.now() - shb_time).total_seconds()
                components['scheduler_heartbeat'] = {
                    'status': 'ok' if s_age_seconds <= 180 else 'stale',
                    'last_heartbeat': last_shb,
                    'age_seconds': round(s_age_seconds, 1),
                }
            else:
                components['scheduler_heartbeat'] = {
                    'status': 'inactive',
                    'detail': 'No scheduler heartbeat recorded yet',
                }
        except Exception as exc:
            components['scheduler_heartbeat'] = {
                'status': 'unknown',
                'error': str(exc),
            }
    else:
        components['scheduler_heartbeat'] = {
            'status': 'inactive',
            'detail': 'Cache unreachable; scheduler heartbeat cannot be retrieved',
        }

    is_healthy = components['web']['status'] == 'ok' and components['database']['status'] == 'ok'
    status_code = 200 if is_healthy else 503

    return JsonResponse({
        'status': 'ok' if is_healthy else 'unhealthy',
        'timestamp': timezone.now().isoformat(),
        'components': components,
    }, status=status_code)


def operations_view(request):
    """
    Operations dashboard displaying:
    - Worker and scheduler heartbeat status
    - Cache & broker connectivity and latency when Redis is configured
    - Daily budget tracking (Africa/Lagos calendar)
    - Provider circuit breaker status
    - Per-site sync timeline & retry schedule
    - Recent sync attempt log
    Gracefully degrades if cache or broker is unreachable.
    """
    now = timezone.now()
    forecast_runner = settings.FORECAST_RUNNER
    scheduled_run = scheduled_forecast_status(now) if forecast_runner == 'github_actions' else None
    now_lagos = now.astimezone(LAGOS_TZ)
    today_lagos = now_lagos.date()

    cache_health = None
    if not settings.DEMO_MODE and settings.REDIS_URL:
        cache_health = {'status': 'ok', 'latency_ms': None, 'detail': 'Connected to Redis'}
        t0 = timezone.now()
        try:
            cache.set('crewcast:health:ping', 'pong', timeout=10)
            if cache.get('crewcast:health:ping') == 'pong':
                cache_health['latency_ms'] = round((timezone.now() - t0).total_seconds() * 1000, 2)
            else:
                cache_health['status'] = 'degraded'
                cache_health['detail'] = 'Cache read mismatch'
        except Exception as exc:
            cache_health['status'] = 'degraded'
            cache_health['detail'] = f'Redis unreachable ({exc})'

    # 1. Worker Heartbeat
    worker_hb = {'status': 'inactive', 'last_seen': None, 'age_display': 'Never seen'}
    try:
        w_val = cache.get(WORKER_HEARTBEAT_CACHE_KEY)
        if w_val:
            w_dt = datetime.fromisoformat(w_val)
            w_age = max(0.0, (now - w_dt).total_seconds())
            worker_hb['last_seen'] = w_dt.astimezone(LAGOS_TZ).strftime('%H:%M:%S WAT')
            worker_hb['age_display'] = format_duration_ago(w_age)
            worker_hb['status'] = 'ok' if w_age <= 180 else 'stale'
    except Exception:
        worker_hb['status'] = 'degraded'
        worker_hb['age_display'] = 'Cache unreachable'

    # 3. Scheduler Heartbeat
    scheduler_hb = {'status': 'inactive', 'last_seen': None, 'age_display': 'Never seen'}
    try:
        s_val = cache.get(SCHEDULER_HEARTBEAT_CACHE_KEY)
        if s_val:
            s_dt = datetime.fromisoformat(s_val)
            s_age = max(0.0, (now - s_dt).total_seconds())
            scheduler_hb['last_seen'] = s_dt.astimezone(LAGOS_TZ).strftime('%H:%M:%S WAT')
            scheduler_hb['age_display'] = format_duration_ago(s_age)
            scheduler_hb['status'] = 'ok' if s_age <= 180 else 'stale'
    except Exception:
        scheduler_hb['status'] = 'degraded'
        scheduler_hb['age_display'] = 'Cache unreachable'

    # 4. Daily Budget (Africa/Lagos)
    budget = BudgetWindow.objects.filter(lagos_date=today_lagos).first()
    reserved = budget.reserved_calls if budget else 0
    successful = budget.successful_calls if budget else 0
    failed = budget.failed_calls if budget else 0
    deferred = budget.deferred_calls if budget else 0
    consumed = successful + failed
    remaining = max(0, 300 - reserved)
    pct_used = min(100.0, round((reserved / 300.0) * 100, 1))

    budget_info = {
        'date_display': today_lagos.strftime('%A, %d %B %Y'),
        'cap': 300,
        'reserved': reserved,
        'consumed': consumed,
        'successful': successful,
        'failed': failed,
        'deferred': deferred,
        'remaining': remaining,
        'percentage_used': pct_used,
        'verified': budget is None or budget.source_kind == 'worker',
    }

    # 5. Provider Circuit Breaker
    circuit = ProviderCircuitState.objects.filter(id=1).first() or ProviderCircuitState()
    cooloff_remaining = None
    if circuit.state == 'OPEN' and circuit.opened_at:
        elapsed = (now - circuit.opened_at).total_seconds()
        cooloff_remaining = max(0, int(circuit.cooloff_seconds - elapsed))

    circuit_info = {
        'state': circuit.state,
        'consecutive_failures': circuit.consecutive_transient_failures,
        'opened_at_wat': circuit.opened_at.astimezone(LAGOS_TZ).strftime('%H:%M:%S WAT') if circuit.opened_at else None,
        'cooloff_seconds': circuit.cooloff_seconds,
        'cooloff_remaining_seconds': cooloff_remaining,
        'last_probe_wat': circuit.last_probe_at.astimezone(LAGOS_TZ).strftime('%H:%M:%S WAT') if circuit.last_probe_at else None,
    }

    # 6. Per-Site Sync Timeline
    sites_data = []
    active_sites = Site.objects.filter(is_active=True).order_by('name')
    for site in active_sites:
        current_attempt = latest_verified_success(site)
        verified_sync_at = current_attempt.completed_at if current_attempt else None
        last_sync_wat = verified_sync_at.astimezone(LAGOS_TZ).strftime('%d %b %H:%M WAT') if verified_sync_at else "Never synced"
        if verified_sync_at:
            next_due = verified_sync_at + timedelta(hours=3)
            next_due_wat = next_due.astimezone(LAGOS_TZ).strftime('%d %b %H:%M WAT')
            is_overdue = (next_due <= now)
        else:
            next_due_wat = "Immediate (Pending)"
            is_overdue = True
        f_state, f_age = get_freshness_state(verified_sync_at, now=now)

        latest_attempt = SyncAttempt.objects.filter(site=site, source_kind='worker').order_by('-pk').first()
        last_outcome = latest_attempt.outcome if latest_attempt else "none"
        last_error = latest_attempt.error_message if (latest_attempt and latest_attempt.outcome != 'success') else ""
        next_retry_wat = latest_attempt.next_retry_at.astimezone(LAGOS_TZ).strftime('%H:%M:%S WAT') if (latest_attempt and latest_attempt.next_retry_at and latest_attempt.next_retry_at > now) else None

        sites_data.append({
            'site': site,
            'last_sync_wat': last_sync_wat,
            'last_sync_age': format_duration_ago(f_age) if verified_sync_at else "—",
            'freshness_state': f_state if verified_sync_at else 'pending',
            'next_due_wat': next_due_wat,
            'is_overdue': is_overdue,
            'last_outcome': last_outcome,
            'last_error': last_error,
            'next_retry_wat': next_retry_wat,
        })

    # 7. Recent Sync Attempts Log
    recent_attempts = []
    for att in SyncAttempt.objects.select_related('site', 'snapshot').filter(
        source_kind='worker'
    ).order_by('-started_at', '-pk')[:20]:
        dur_ms = None
        if att.completed_at and att.started_at:
            dur_ms = round((att.completed_at - att.started_at).total_seconds() * 1000, 1)

        recent_attempts.append({
            'site_name': att.site.name,
            'started_wat': att.started_at.astimezone(LAGOS_TZ).strftime('%d %b %H:%M:%S WAT'),
            'attempt_number': att.attempt_number,
            'outcome': att.outcome,
            'failure_category': att.failure_category,
            'http_status': att.http_status,
            'duration_ms': dur_ms,
            'snapshot_hash': att.snapshot.content_hash[:8] if att.snapshot else None,
            'error_message': att.error_message,
        })

    context = {
        'cache_health': cache_health,
        'worker_hb': worker_hb,
        'scheduler_hb': scheduler_hb,
        'forecast_runner': forecast_runner,
        'scheduled_run': scheduled_run,
        'budget': budget_info,
        'circuit': circuit_info,
        'sites_data': sites_data,
        'recent_attempts': recent_attempts,
        'legacy_unverified_present': (
            ForecastSnapshot.objects.filter(source_kind='unknown').exists()
            or SyncAttempt.objects.filter(source_kind='unknown').exists()
            or BudgetWindow.objects.filter(source_kind='unknown').exists()
        ),
    }
    return render(request, 'core/operations.html', context)


def demo_replay_view(request):
    """
    Simulation & Failure Replay sandbox:
    Allows evaluating canned fixture scenarios without mutating the database:
    1. Normal Success (Clear Sky / Suitable)
    2. Caution Threshold Crossed (Rain / Wind)
    3. Severe Weather / Stop Threshold (Unsuitable)
    4. Transient Timeout & Exponential Backoff Retry
    5. Stale Data Freshness Suppression (7.5h old)
    6. Expired Data (>12h old)
    7. Provider Circuit Breaker Trip & Recovery
    """
    scenario_key = request.GET.get('scenario', 'normal')

    scenarios_list = [
        {'key': 'normal', 'name': '1. Normal Success', 'badge': 'Suitable'},
        {'key': 'caution', 'name': '2. Caution Warning', 'badge': 'Caution'},
        {'key': 'unsuitable', 'name': '3. Severe Rainstorm', 'badge': 'Unsuitable'},
        {'key': 'timeout_retry', 'name': '4. Timeout & Retry', 'badge': 'Backoff'},
        {'key': 'stale', 'name': '5. Stale Data Suppression', 'badge': 'Stale 7.5h'},
        {'key': 'expired', 'name': '6. Expired Data', 'badge': 'Expired 14h'},
        {'key': 'circuit_recovery', 'name': '7. Circuit Breaker', 'badge': 'Circuit Trip'},
    ]

    now = timezone.now()
    now_lagos = now.astimezone(LAGOS_TZ)

    sim_title = ""
    sim_desc = ""
    sim_site = "Victoria Island Commercial Depot"
    sim_job_title = "Rooftop Air Handling Unit Overhaul"
    sim_window = "Tomorrow 09:00 – 13:00 WAT"
    sim_freshness_state = "fresh"
    sim_age_text = "Forecast retrieved 24m ago"
    rec_status = "suitable"
    reasons = []
    hourly_evaluations = []
    extra_details = {}

    if scenario_key == 'normal':
        sim_title = "Normal Success (Fair Weather Work Window)"
        sim_desc = "Clear conditions across all 4 hours. Precipitation probability and wind gusts remain well below caution thresholds."
        rec_status = "suitable"
        sim_freshness_state = "fresh"
        sim_age_text = "Forecast retrieved 35m ago"
        hourly_evaluations = [
            {'hour_label': '09:00–10:00 WAT', 'prob': 10, 'precip': 0.0, 'gusts': 12.0, 'temp': 27.5},
            {'hour_label': '10:00–11:00 WAT', 'prob': 15, 'precip': 0.0, 'gusts': 14.5, 'temp': 28.2},
            {'hour_label': '11:00–12:00 WAT', 'prob': 15, 'precip': 0.2, 'gusts': 16.0, 'temp': 29.0},
            {'hour_label': '12:00–13:00 WAT', 'prob': 20, 'precip': 0.1, 'gusts': 18.0, 'temp': 29.8},
        ]
        reasons = []

    elif scenario_key == 'caution':
        sim_title = "Caution Thresholds Crossed (Moderate Rain & Wind)"
        sim_desc = "Rain probability reaches 55% (caution threshold: 40%) and wind gusts reach 28.0 km/h (caution threshold: 25.0 km/h). Supervisor review advised."
        rec_status = "caution"
        sim_freshness_state = "fresh"
        sim_age_text = "Forecast retrieved 1h 10m ago"
        hourly_evaluations = [
            {'hour_label': '09:00–10:00 WAT', 'prob': 25, 'precip': 0.2, 'gusts': 18.0, 'temp': 28.0},
            {'hour_label': '10:00–11:00 WAT', 'prob': 45, 'precip': 1.1, 'gusts': 22.0, 'temp': 28.5},
            {'hour_label': '11:00–12:00 WAT', 'prob': 55, 'precip': 1.8, 'gusts': 28.0, 'temp': 27.8},
            {'hour_label': '12:00–13:00 WAT', 'prob': 50, 'precip': 1.4, 'gusts': 26.5, 'temp': 28.1},
        ]
        reasons = [
            {'metric': 'precipitation_probability', 'level': 'caution', 'observed_value': 55.0, 'threshold_value': 40.0, 'unit': '%', 'hour_label_wat': '11:00–12:00 WAT', 'message': 'Rain probability reached 55% (caution: 40%) during 11:00–12:00 WAT'},
            {'metric': 'wind_gusts_10m', 'level': 'caution', 'observed_value': 28.0, 'threshold_value': 25.0, 'unit': 'km/h', 'hour_label_wat': '11:00–12:00 WAT', 'message': 'Wind gusts reached 28.0 km/h (caution: 25.0 km/h) during 11:00–12:00 WAT'},
        ]

    elif scenario_key == 'unsuitable':
        sim_title = "Severe Tropical Rainstorm (Stop Work Threshold)"
        sim_desc = "Precipitation reaches 7.5 mm/h (stop: 5.0 mm/h) and rain probability peaks at 85% (stop: 70%). Immediate stop work recommendation."
        rec_status = "unsuitable"
        sim_freshness_state = "fresh"
        sim_age_text = "Forecast retrieved 45m ago"
        hourly_evaluations = [
            {'hour_label': '09:00–10:00 WAT', 'prob': 40, 'precip': 1.5, 'gusts': 22.0, 'temp': 27.5},
            {'hour_label': '10:00–11:00 WAT', 'prob': 85, 'precip': 7.5, 'gusts': 44.0, 'temp': 26.0},
            {'hour_label': '11:00–12:00 WAT', 'prob': 80, 'precip': 5.8, 'gusts': 38.0, 'temp': 25.8},
            {'hour_label': '12:00–13:00 WAT', 'prob': 65, 'precip': 3.2, 'gusts': 26.0, 'temp': 26.5},
        ]
        reasons = [
            {'metric': 'precipitation', 'level': 'stop', 'observed_value': 7.5, 'threshold_value': 5.0, 'unit': 'mm/h', 'hour_label_wat': '10:00–11:00 WAT', 'message': 'Precipitation reached 7.5 mm/h (stop: 5.0 mm/h) during 10:00–11:00 WAT'},
            {'metric': 'precipitation_probability', 'level': 'stop', 'observed_value': 85.0, 'threshold_value': 70.0, 'unit': '%', 'hour_label_wat': '10:00–11:00 WAT', 'message': 'Rain probability reached 85% (stop: 70%) during 10:00–11:00 WAT'},
            {'metric': 'wind_gusts_10m', 'level': 'stop', 'observed_value': 44.0, 'threshold_value': 40.0, 'unit': 'km/h', 'hour_label_wat': '10:00–11:00 WAT', 'message': 'Wind gusts reached 44.0 km/h (stop: 40.0 km/h) during 10:00–11:00 WAT'},
        ]

    elif scenario_key == 'timeout_retry':
        sim_title = "Transient Upstream Timeout & Exponential Backoff"
        sim_desc = "Simulates Open-Meteo HTTP 504 Gateway Timeout during site sync attempt. Shows transient failure classification, slot budgeting, and scheduled retry."
        rec_status = "suitable"
        sim_freshness_state = "fresh"
        sim_age_text = "Forecast retrieved 2h 45m ago (Prior Snapshot)"
        extra_details = {
            'is_retry_simulation': True,
            'failure_error': 'HTTP 504 Gateway Timeout: provider timed out after 10.0s',
            'attempt_number': 1,
            'max_attempts': 3,
            'calculated_delay_seconds': 45,
            'next_retry_wat': (now_lagos + timedelta(seconds=45)).strftime('%H:%M:%S WAT'),
            'cached_snapshot_preserved': True,
        }

    elif scenario_key == 'stale':
        sim_title = "Stale Forecast (7.5h Old) — Suitable Suppression Rule"
        sim_desc = "Demonstrates strict CrewCast safety invariant: when forecast age exceeds 4 hours, a 'suitable' rating is suppressed into 'Historical context (Stale)'."
        rec_status = "suitable"
        sim_freshness_state = "stale"
        sim_age_text = "Forecast retrieved 7h 30m ago"
        hourly_evaluations = [
            {'hour_label': '09:00–10:00 WAT', 'prob': 15, 'precip': 0.1, 'gusts': 14.0, 'temp': 28.0},
            {'hour_label': '10:00–11:00 WAT', 'prob': 20, 'precip': 0.2, 'gusts': 16.0, 'temp': 28.5},
            {'hour_label': '11:00–12:00 WAT', 'prob': 18, 'precip': 0.0, 'gusts': 15.0, 'temp': 29.1},
            {'hour_label': '12:00–13:00 WAT', 'prob': 22, 'precip': 0.3, 'gusts': 17.0, 'temp': 29.4},
        ]
        reasons = []

    elif scenario_key == 'expired':
        sim_title = "Expired Forecast (14h Old) — No Current Recommendation"
        sim_desc = "Forecast data older than 12 hours is expired. The system displays 'No current recommendation' and instructs the crew to await a fresh synchronization."
        rec_status = "suitable"
        sim_freshness_state = "expired"
        sim_age_text = "Forecast retrieved 14h 10m ago"
        reasons = []

    elif scenario_key == 'circuit_recovery':
        sim_title = "Provider Circuit Breaker Trip & Recovery Lifecycle"
        sim_desc = "Simulates 3 consecutive transient provider errors tripping the circuit breaker from CLOSED to OPEN (15-min cooloff), testing a HALF-OPEN probe, and resetting."
        rec_status = "unsuitable"
        sim_freshness_state = "fresh"
        sim_age_text = "Forecast retrieved 1h 0m ago"
        extra_details = {
            'is_circuit_simulation': True,
            'transitions': [
                {'stage': '1. Normal', 'state': 'CLOSED', 'failures': 0, 'desc': 'Outbound calls proceed normally within daily budget.'},
                {'stage': '2. 3 Failures', 'state': 'OPEN', 'failures': 3, 'desc': 'Circuit trips to OPEN after 3 timeouts. Outbound calls deferred for 15 minutes.'},
                {'stage': '3. Probe', 'state': 'HALF_OPEN', 'failures': 3, 'desc': 'Cool-off expires; worker sends exactly 1 test request to Open-Meteo.'},
                {'stage': '4. Recovery', 'state': 'CLOSED', 'failures': 0, 'desc': 'Probe succeeds! Circuit closes, consecutive failures reset to 0.'},
            ]
        }

    effective_display = get_effective_planning_display(rec_status, sim_freshness_state)

    context = {
        'scenario_key': scenario_key,
        'scenarios_list': scenarios_list,
        'sim_title': sim_title,
        'sim_desc': sim_desc,
        'sim_site': sim_site,
        'sim_job_title': sim_job_title,
        'sim_window': sim_window,
        'sim_freshness_state': sim_freshness_state,
        'sim_age_text': sim_age_text,
        'rec_status': rec_status,
        'effective_display': effective_display,
        'reasons': reasons,
        'hourly_evaluations': hourly_evaluations,
        'extra_details': extra_details,
    }
    return render(request, 'core/demo_replay.html', context)
