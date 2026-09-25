from django import forms
from django.utils import timezone
from .models import Site, Job, WeatherPolicyVersion, LAGOS_TZ

class JobForm(forms.ModelForm):
    start_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        help_text="Start time in Africa/Lagos (WAT)"
    )
    end_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        help_text="End time in Africa/Lagos (WAT)"
    )

    class Meta:
        model = Job
        fields = ['site', 'title', 'start_time', 'end_time']
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Facade Window Cleaning'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['site'].queryset = Site.objects.filter(is_active=True)

    def clean_start_time(self):
        val = self.cleaned_data.get('start_time')
        if val and timezone.is_naive(val):
            val = timezone.make_aware(val, LAGOS_TZ)
        return val

    def clean_end_time(self):
        val = self.cleaned_data.get('end_time')
        if val and timezone.is_naive(val):
            val = timezone.make_aware(val, LAGOS_TZ)
        return val


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ['name', 'latitude', 'longitude', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.000001'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }


class WeatherPolicyForm(forms.ModelForm):
    class Meta:
        model = WeatherPolicyVersion
        fields = [
            'rain_prob_caution', 'rain_prob_stop',
            'precip_caution_mm', 'precip_stop_mm',
            'gust_caution_kmh', 'gust_stop_kmh',
            'apparent_temp_caution_c', 'apparent_temp_stop_c'
        ]
        widgets = {f: forms.NumberInput(attrs={'class': 'form-input'}) for f in fields}

    def save(self, commit=True):
        # Always create a new version; never update an existing record
        instance = WeatherPolicyVersion(
            rain_prob_caution=self.cleaned_data['rain_prob_caution'],
            rain_prob_stop=self.cleaned_data['rain_prob_stop'],
            precip_caution_mm=self.cleaned_data['precip_caution_mm'],
            precip_stop_mm=self.cleaned_data['precip_stop_mm'],
            gust_caution_kmh=self.cleaned_data['gust_caution_kmh'],
            gust_stop_kmh=self.cleaned_data['gust_stop_kmh'],
            apparent_temp_caution_c=self.cleaned_data['apparent_temp_caution_c'],
            apparent_temp_stop_c=self.cleaned_data['apparent_temp_stop_c'],
        )
        if commit:
            instance.save()
        return instance
