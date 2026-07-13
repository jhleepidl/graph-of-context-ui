# User-path optimization acceptance scenarios

## 1. Idle request volume

1. Open Room Work with no active run.
2. Observe browser Network for 30 seconds.
3. Confirm the graph endpoint is not repeatedly called on Room Work.
4. Confirm summary refresh backs off instead of running every 1.5 seconds.
5. Hide the tab for 30 seconds and return.

Pass: no overlapping refreshes, no graph polling on Room Work, and a prompt refresh after returning.

## 2. Active work responsiveness

1. Start a normal Room task.
2. Keep GoC open.
3. Confirm status changes appear within a few seconds.
4. Confirm details do not flash or reset on every summary refresh.

Pass: summary remains responsive while detail requests are less frequent.

## 3. Long-running message

1. Send a task expected to run longer than 30 seconds from GoC chat.
2. Observe queued and accepted states.
3. Wait at least 45 seconds.

Pass: the UI shows Room work in progress and does not report a false failure at 30 seconds.

## 4. Network retry and duplicate protection

1. In browser devtools, block the first POST to `/api/runtime/commands` after it reaches the server, or simulate a lost response.
2. Retry using the same UI action.
3. Inspect runtime commands.

Pass: a client-generated `command_id` exists and the same ID resolves to one command.

## 5. Room switch race

1. Open Room A while its summary endpoint is artificially delayed.
2. Immediately switch to Room B.
3. Allow Room A response to complete.

Pass: Room B remains displayed; Room A data does not overwrite it.

## 6. Incremental chat projection

1. Open chat and inspect the first runtime event request.
2. Send a message.
3. Inspect later requests.

Pass: later requests include `after_event_id` and contain only new events.

## 7. Projection outage recovery

1. Temporarily make GoC runtime event ingest fail.
2. Complete a Room run.
3. Restore GoC.
4. Wait for retry or trigger the next event flush.

Pass: local runtime history remains complete, events arrive in original sequence, and duplicates do not create duplicate projections.
