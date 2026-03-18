function cleanText(value: unknown): string { return typeof value === 'string' ? value.trim() : String(value || '').trim() }
function cleanId(value: unknown): string { return cleanText(value).toLowerCase() }
const roleLabels: Record<string, string> = { researcher: '조사', builder: '구현', reviewer: '검토', synthesizer: '최종 정리', operator: '진행 운영' }
const executionPatternLabels: Record<string, string> = {
  single_specialist: '단일 전문 agent가 바로 처리',
  sequential_pipeline: '순차 파이프라인',
  parallel_research_then_review_then_synthesize: '병렬 조사 → 검토 → 최종 정리',
  builder_reviewer_loop: '구현 ↔ 검토 반복',
  multi_research_adjudication: '다중 조사 → 조정',
  operator_gated_workflow: '운영 게이트 포함 워크플로우',
}
const visibilityLabels: Record<string, string> = {
  summary_only: '요약만 확인',
  summaries_plus_selected_evidence: '요약 + 선택된 핵심 근거',
  upstream_outputs_only: '상위 결과물만 확인',
  full_context: '전체 문맥 확인',
}
const payloadLabels: Record<string, string> = {
  summary_only: '요약',
  summary_plus_key_evidence: '요약 + 핵심 근거',
  review_summary_only: '검토 요약',
  approved_summary_only: '승인된 요약',
  draft_plus_change_summary: '초안 + 변경 요약',
}
const skillLabels: Record<string, { label: string }> = {
  web_search: { label: '웹 조사' }, source_triage: { label: '출처 선별' }, evidence_mapping: { label: '근거 정리' }, news_clustering: { label: '뉴스 묶음화' },
  dart_analysis: { label: '공시 해석' }, table_extraction: { label: '표 추출' }, financial_comparison: { label: '재무 비교' }, contradiction_check: { label: '모순 점검' },
  adversarial_review: { label: '반박 검토' }, evidence_validation: { label: '근거 검증' }, structured_summary: { label: '구조화 요약' }, report_synthesis: { label: '최종 보고서 작성' },
  approval_gate: { label: '승인 게이트' }, run_control: { label: '실행 제어' }, code_editing: { label: '코드 수정' }, implementation_planning: { label: '구현 설계' },
  market_mapping: { label: '시장 지도 작성' }, company_screening: { label: '종목 스크리닝' }, catalyst_mapping: { label: '촉매 추적' }, market_news_scan: { label: '시장 뉴스 스캔' },
  thesis_stress_test: { label: '투자 논리 스트레스 테스트' }, upside_case_building: { label: '상승 시나리오 설계' }, downside_case_building: { label: '하락 시나리오 설계' },
  risk_signal_mapping: { label: '리스크 신호 추적' }, growth_signal_mapping: { label: '성장 신호 추적' }, investment_synthesis: { label: '투자 결론 정리' }, portfolio_briefing: { label: '포트폴리오 브리핑' },
}
export function roleLabel(roleId: unknown): string { return roleLabels[cleanId(roleId)] || cleanText(roleId) || '역할 미지정' }
export function humanizeExecutionPattern(pattern: unknown): string { return executionPatternLabels[cleanId(pattern)] || cleanText(pattern) || '미정' }
export function humanizeVisibility(value: unknown): string { return visibilityLabels[cleanId(value)] || cleanText(value) || '미정' }
export function humanizePayload(value: unknown): string { return payloadLabels[cleanId(value)] || cleanText(value) || '요약' }
export function humanizeSkill(skillId: unknown): string { const key = cleanId(skillId); const meta = skillLabels[key]; if (meta) return meta.label; const raw = cleanText(skillId); return raw ? raw.replace(/[_-]+/g, ' ') : 'Unnamed skill' }
export function humanizeModel(provider: unknown, model: unknown): string {
  const providerText = cleanId(provider); const modelText = cleanText(model)
  const providerLabel = providerText === 'chatgpt' ? 'ChatGPT' : providerText === 'gemini' ? 'Gemini' : providerText === 'codex' ? 'Codex' : providerText
  const modelLabel = modelText.replace(/^gemini-2\.5-pro$/i, 'Gemini 2.5 Pro').replace(/^gpt-5-codex$/i, 'GPT-5 Codex').replace(/^gpt-5\.4$/i, 'GPT-5.4')
  if (!providerLabel && !modelLabel) return '-'; if (!providerLabel) return modelLabel; if (!modelLabel) return providerLabel; return `${providerLabel} · ${modelLabel}`
}
