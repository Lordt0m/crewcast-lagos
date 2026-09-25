from decimal import Decimal
import pytest
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User
from django.test import Client
from core.models import Site, Job, WeatherPolicyVersion, LAGOS_TZ, MAX_ACTIVE_SITES

@pytest.fixture
def default_policy(db):
    return WeatherPolicyVersion.objects.create(
        rain_prob_caution=40,
        rain_prob_stop=70,
        precip_caution_mm=Decimal("2.00"),
        precip_stop_mm=Decimal("5.00"),
        gust_caution_kmh=Decimal("25.00"),
        gust_stop_kmh=Decimal("40.00"),
        apparent_temp_caution_c=Decimal("30.00"),
        apparent_temp_stop_c=Decimal("35.00"),
    )

@pytest.fixture
def valid_site(db):
    return Site.objects.create(
        name="Lekki Phase 1 Depot",
        latitude=Decimal("6.447400"),
        longitude=Decimal("3.472300"),
        is_active=True,
    )

@pytest.fixture
def manager_user(db):
    return User.objects.create_user(username="manager", password="password123")


@pytest.mark.django_db
class TestSiteModel:
    def test_valid_site_creation(self, valid_site):
        assert valid_site.pk is not None
        assert str(valid_site) == "Lekki Phase 1 Depot"

    def test_site_outside_lagos_rejected(self):
        # Abuja coordinates (~9.07N, 7.49E)
        site = Site(name="Abuja Branch", latitude=Decimal("9.070000"), longitude=Decimal("7.490000"))
        with pytest.raises(ValidationError) as exc:
            site.full_clean()
        assert "Lagos area" in str(exc.value)

    def test_active_sites_limit_enforced(self):
        # Create 10 active sites
        for i in range(MAX_ACTIVE_SITES):
            Site.objects.create(
                name=f"Site {i+1}",
                latitude=Decimal("6.450000"),
                longitude=Decimal("3.450000"),
                is_active=True
            )
        # Attempt to create the 11th active site
        site_11 = Site(
            name="Site 11 Over Limit",
            latitude=Decimal("6.450000"),
            longitude=Decimal("3.450000"),
            is_active=True
        )
        with pytest.raises(ValidationError) as exc:
            site_11.clean()
        assert f"at most {MAX_ACTIVE_SITES} active sites" in str(exc.value)


@pytest.mark.django_db
class TestWeatherPolicyVersion:
    def test_valid_policy_creation(self, default_policy):
        assert default_policy.pk is not None

    def test_invalid_threshold_order_rejected(self):
        # Caution >= Stop
        bad_policy = WeatherPolicyVersion(
            rain_prob_caution=70,
            rain_prob_stop=40, # Invalid: caution > stop
            precip_caution_mm=Decimal("2.00"),
            precip_stop_mm=Decimal("5.00"),
            gust_caution_kmh=Decimal("25.00"),
            gust_stop_kmh=Decimal("40.00"),
            apparent_temp_caution_c=Decimal("30.00"),
            apparent_temp_stop_c=Decimal("35.00"),
        )
        with pytest.raises(ValidationError) as exc:
            bad_policy.clean()
        assert "rain_prob_caution" in exc.value.error_dict

    def test_policy_immutability_prevents_rewrite(self, default_policy):
        # Attempt to change thresholds in place
        default_policy.rain_prob_caution = 50
        with pytest.raises(ValidationError) as exc:
            default_policy.save()
        assert "immutable" in str(exc.value)


@pytest.mark.django_db
class TestJobModel:
    def test_valid_job_creation_and_revision_increment(self, valid_site, default_policy):
        now_lagos = timezone.now().astimezone(LAGOS_TZ)
        start = (now_lagos + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        end = (now_lagos + timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)

        job = Job.objects.create(
            site=valid_site,
            title="Solar Panel Inspection",
            start_time=start,
            end_time=end,
            policy_version=default_policy,
        )
        assert job.revision == 1

        # Save again (edit)
        job.title = "Solar Panel Deep Inspection"
        job.save()
        assert job.revision == 2

    def test_reject_end_before_start(self, valid_site, default_policy):
        now_lagos = timezone.now().astimezone(LAGOS_TZ)
        start = (now_lagos + timedelta(days=1)).replace(hour=14, minute=0)
        end = (now_lagos + timedelta(days=1)).replace(hour=10, minute=0) # End before start

        job = Job(
            site=valid_site,
            title="Invalid Window Job",
            start_time=start,
            end_time=end,
            policy_version=default_policy,
        )
        with pytest.raises(ValidationError) as exc:
            job.full_clean()
        assert "end_time" in exc.value.error_dict

    def test_reject_out_of_horizon_job(self, valid_site, default_policy):
        now_lagos = timezone.now().astimezone(LAGOS_TZ)
        start = (now_lagos + timedelta(days=10)).replace(hour=9, minute=0) # 10 days out
        end = (now_lagos + timedelta(days=10)).replace(hour=12, minute=0)

        job = Job(
            site=valid_site,
            title="Far Future Job",
            start_time=start,
            end_time=end,
            policy_version=default_policy,
        )
        with pytest.raises(ValidationError) as exc:
            job.full_clean()
        assert "7-day planning horizon" in str(exc.value)

    def test_reject_past_job(self, valid_site, default_policy):
        now_lagos = timezone.now().astimezone(LAGOS_TZ)
        start = (now_lagos - timedelta(days=2)).replace(hour=9, minute=0)
        end = (now_lagos - timedelta(days=2)).replace(hour=12, minute=0)

        job = Job(
            site=valid_site,
            title="Past Job",
            start_time=start,
            end_time=end,
            policy_version=default_policy,
        )
        with pytest.raises(ValidationError) as exc:
            job.full_clean()
        assert "start_time" in exc.value.error_dict


@pytest.mark.django_db
class TestAuthorizationAndDemoMode:
    def test_unauthorized_user_redirected_on_mutation(self, client):
        response = client.post('/jobs/new/', {
            'title': 'Unauthorized Job',
        })
        assert response.status_code == 302
        assert '/login/' in response.url
        assert Job.objects.count() == 0

    def test_demo_mode_blocks_authenticated_mutations(self, client, manager_user, valid_site, settings):
        settings.DEMO_MODE = True
        client.force_login(manager_user)

        now_lagos = timezone.now().astimezone(LAGOS_TZ)
        start = (now_lagos + timedelta(days=1)).strftime("%Y-%m-%dT09:00")
        end = (now_lagos + timedelta(days=1)).strftime("%Y-%m-%dT12:00")

        response = client.post('/jobs/new/', {
            'site': valid_site.pk,
            'title': 'Attempted Demo Job',
            'start_time': start,
            'end_time': end,
        })
        assert response.status_code == 403
        assert Job.objects.count() == 0
