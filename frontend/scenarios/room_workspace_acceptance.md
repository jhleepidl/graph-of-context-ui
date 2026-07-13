# GoC Room Workspace acceptance scenarios

These scenarios validate generic Room continuity, progressive disclosure, and shared-runtime chat. They do not depend on coding, finance, recommendation, research, or any other domain keyword rule.

## Prerequisites

- GoC backend and frontend are running.
- ddalggak points to the same GoC instance.
- The selected GoC thread has a Telegram `external_ref` or Telegram chat metadata.
- The existing command worker is enabled:

```env
GOC_RUNTIME_COMMAND_POLL_ENABLED=true
```

- Runtime event synchronization is operating so assistant replies can be projected back to GoC.
- Restart ddalggak after changing runtime settings.

Record the browser size, GoC/ddalggak commits, selected Room ID, runtime command IDs, and screenshots.

## Scenario 1 — folded first view

1. Open GoC and select a Room with active work and review items.
2. Do not click any fold row.
3. Identify the current goal and next action.
4. Count how many expanded detail panels are visible below them.

Pass when:

- the goal and next action are visible immediately;
- 작업방 채팅, 진행 중인 작업, 확인할 항목, and advanced details are closed by default;
- pending counts remain visible on closed rows;
- the user is not required to scroll through long panel contents.

## Scenario 2 — expand only what is needed

1. Expand **진행 중인 작업**.
2. Confirm its contents appear and other folded sections stay closed.
3. Close it again.
4. Reload the page.

Pass when:

- only the selected section expands;
- the row exposes `aria-expanded` correctly;
- the chosen open/closed state is remembered after reload for that Room;
- the section can be operated by keyboard.

## Scenario 3 — plain-language navigation

Without opening the terminology guide, ask a first-time user to locate:

1. materials the Room may use;
2. instructions the Room must keep following;
3. changes waiting for approval;
4. the place to continue the conversation.

Pass when the user can choose **참고 자료**, **기억과 규칙**, **확인 필요**, and **작업방 채팅** without needing the terms Source, Context set, Correction, Projection, or Review inbox.

Then expand **용어가 어렵다면 보기** and confirm its explanations are understandable without runtime knowledge.

## Scenario 4 — read recent Room conversation

1. Exchange at least one user/assistant turn through Telegram.
2. Open the same Room in GoC.
3. Expand **작업방 채팅**.
4. Select **새로고침** if necessary.

Pass when:

- the most recent user and assistant turns appear in chronological order;
- the chat panel was closed before the user asked for it;
- no second Room/session identity is created;
- the same answer remains visible in Telegram.

## Scenario 5 — send a normal message from GoC

1. Expand **작업방 채팅**.
2. Send: `이전 계획을 이어서 첫 번째 단계만 진행해줘.`
3. Observe the delivery status.
4. Wait for the assistant reply or refresh the panel.
5. Check Telegram.

Pass when:

- a `room_message` runtime command moves from queued/claimed to applied;
- the message enters the same ddalggak Room path as a Telegram message;
- the assistant answer appears in Telegram;
- the projected answer later appears in GoC without creating a separate provider execution path;
- the Room's prior goal, rules, and source boundary still apply.

Projection may lag. Record command delivery and Telegram response separately from GoC display latency.

## Scenario 6 — chat does not bypass governed commands

1. Enter `/stop` or `/correct test` into 작업방 채팅.
2. Try to send it.
3. Open **작업방 수정** and select a supported correction action instead.

Pass when:

- chat refuses slash commands before delivery;
- 작업방 수정 remains the path for bounded continuity commands;
- unsupported operational commands are not executed by the runtime worker.

## Scenario 7 — record a correction from GoC

1. Select **작업방 수정**.
2. Choose **잘못 이해한 점 수정**.
3. Enter: `이번 UI 테스트에서는 backend schema를 변경하지 마.`
4. Select **작업방에 적용**.
5. Wait for `applied`.
6. Open **기억과 규칙** and refresh.
7. Send a follow-up from GoC chat.

Pass when the correction is visible in Telegram/Room state and the next response respects it without manual database editing.

Fallback test: disable the worker, repeat the action, and verify that the UI explains the queued state and still allows command copying.

## Scenario 8 — exclude a stale source

1. Open **참고 자료**.
2. Expand only the source-boundary section needed for the test.
3. Use an inline **자료 제외** action when available; otherwise use 작업방 수정.
4. Confirm the selected source is prefilled.
5. Apply the change and compare with Telegram `/sources`.
6. Ask a follow-up in GoC chat that would expose use of the stale source.

Pass when the excluded item is no longer treated as trusted, unrelated sources remain active, and the next response follows the updated boundary.

## Scenario 9 — preserve the main direction while branching

1. Record the current goal.
2. Select **작업방 수정 > 다른 방향 만들기**.
3. Enter: `현재 방향은 유지하고, local-first 대안을 별도로 비교해.`
4. Apply the change.
5. Refresh **지금** and **변경 기록**.

Pass when the original goal remains active and the alternative is represented separately rather than silently replacing the main direction.

## Scenario 10 — narrow-screen use

1. Open GoC at approximately 390 × 844 CSS pixels or on a phone.
2. Verify the Room header and section navigation.
3. Expand and close 작업방 채팅.
4. Enter a short message but do not send confidential data.
5. Open 작업방 수정.

Pass when:

- there is no horizontal page scrolling;
- folded rows and badges remain readable;
- the chat composer and buttons remain usable;
- the drawer remains operable;
- important daily actions do not require opening 고급 설정.

## Scenario 11 — direct worker unavailable

1. Temporarily disable `GOC_RUNTIME_COMMAND_POLL_ENABLED` in staging and restart ddalggak.
2. Send a normal GoC chat message and submit a correction.
3. Observe each status and fallback guidance.

Pass when the UI does not pretend the action completed, does not spin forever, and makes it clear that Telegram remains available. Restore the setting after the test.

## Handoff evidence

Save:

- browser/device size;
- GoC and ddalggak commit IDs;
- screenshots of folded and expanded states;
- runtime command ID, type, and final status;
- Telegram user message and assistant reply;
- GoC event-projection delay;
- any term the tester could not understand;
- any section opened unnecessarily;
- any duplicate or mismatched conversation turn.

Never include `.env`, service keys, Telegram bot tokens, provider credentials, or private unrelated conversation data.
