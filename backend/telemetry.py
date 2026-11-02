"""Optional OTLP traces: identifiers and timings only, never prompts or tokens."""
import os
os.environ.setdefault('OTEL_LOGS_EXPORTER','none')
os.environ.setdefault('OTEL_METRICS_EXPORTER','none')
from opentelemetry import trace
tracer=trace.get_tracer('enterprise-rag')
_configured=False

def configure(service):
    global _configured
    endpoint=os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT','')
    if not endpoint or _configured:return
    os.environ.setdefault('OTEL_SERVICE_NAME',service)
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    provider=TracerProvider(resource=Resource.create({'service.name':service}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip('/')+'/v1/traces')))
    trace.set_tracer_provider(provider)
    _configured=True

def trace_id():
    context=trace.get_current_span().get_span_context()
    return format(context.trace_id,'032x') if context.is_valid else ''
