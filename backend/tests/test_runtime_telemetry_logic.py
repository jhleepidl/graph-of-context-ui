from app.services.runtime_telemetry import build_runtime_telemetry_event, summarize_runtime_telemetry, validate_runtime_telemetry_event


def test_runtime_telemetry_event_uses_actual_openai_usage_and_strips_raw_text():
    event = build_runtime_telemetry_event(
        thread_id='thread-1',
        provider='openai',
        api='responses',
        model='fixed-model',
        usage={
            'input_tokens': 10,
            'output_tokens': 5,
            'total_tokens': 15,
            'input_tokens_details': {'cached_tokens': 2},
            'output_tokens_details': {'reasoning_tokens': 1},
        },
        route={'depth': 'ask', 'raw_text': 'secret'},
        room_memory_trials={'treatment_id': 'T3', 'prompt': 'secret'},
    )
    encoded = str(event)
    assert event['tokens']['token_source'] == 'actual_api_response'
    assert event['tokens']['cached_input_tokens'] == 2
    assert event['tokens']['reasoning_tokens'] == 1
    assert 'secret' not in encoded
    assert validate_runtime_telemetry_event(event) == (True, '')


def test_runtime_telemetry_summary_counts_actual_usage():
    event = build_runtime_telemetry_event(provider='openai', api='responses', usage={'input_tokens': 1, 'output_tokens': 2, 'total_tokens': 3}, latency_ms=100)
    summary = summarize_runtime_telemetry([event])
    assert summary['event_count'] == 1
    assert summary['actual_usage_event_count'] == 1
    assert summary['total_tokens'] == 3
    assert summary['total_latency_ms'] == 100
