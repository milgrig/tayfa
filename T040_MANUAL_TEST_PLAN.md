# T040: Agent Load Dashboard - Manual Test Plan

## Overview
This document provides manual testing procedures for the Agent Load Dashboard frontend widget, including auto-refresh functionality, rendering, and edge case handling.

## Prerequisites
- Tayfa orchestrator running (http://localhost:8000)
- At least 2 agents configured in employees.json
- Access to browser developer console for monitoring

## Test Procedures

### Test 1: Frontend Widget Auto-Refresh (5s interval)

**Objective**: Verify that the widget updates every 5 seconds without flicker

**Steps**:
1. Start the Tayfa orchestrator server
2. Open the web interface at http://localhost:8000
3. Click on "📊 Agent Load" button in the sidebar
4. Observe the "Auto-refresh: 5s" indicator in the header
5. Watch the widget for at least 30 seconds

**Expected Results**:
- ✅ Widget content refreshes every 5 seconds
- ✅ No visible flicker or "flash of unstyled content"
- ✅ Transitions between updates are smooth
- ✅ Data updates in place without full page reload
- ✅ Console shows no errors

**How to Verify**:
- Open browser DevTools (F12) → Network tab
- Filter by "metrics" to see API calls
- Should see GET /api/agents/metrics?window=60 every 5 seconds
- Response time should be < 500ms

---

### Test 2: Time Window Switching

**Objective**: Verify that switching between time windows works correctly

**Steps**:
1. Navigate to Agent Load screen
2. Click "Last 60s" tab - note the metrics displayed
3. Click "Last 10 min" tab - observe metrics change
4. Click "Total session" tab - observe cumulative metrics
5. Switch back to "Last 60s"

**Expected Results**:
- ✅ Active tab is highlighted with visual indicator
- ✅ Metrics update immediately when switching tabs
- ✅ Request counts are higher for longer time windows
- ✅ Cost values are higher for longer time windows
- ✅ No API calls are made on tab switch (uses cached data)

---

### Test 3: Display with Zero Active Agents

**Objective**: Verify proper display when no agents are active

**Steps**:
1. Ensure no agents are running tasks (check Task Board)
2. Navigate to Agent Load screen
3. Observe the display

**Expected Results**:
- ✅ All agents shown with status dot as "idle" (gray/off)
- ✅ Current Task column shows "--" for all agents
- ✅ Totals row shows "Totals (0 busy)"
- ✅ Active Agents widget shows "0 / N" (where N = total agents)
- ✅ No errors in console
- ✅ Widget remains stable and doesn't show loading state repeatedly

---

### Test 4: Display with Multiple Active Agents

**Objective**: Verify proper display when multiple agents are busy

**Setup**:
1. Create 2-3 tasks on the Task Board
2. Assign them to different agents
3. Start execution so agents become busy

**Steps**:
1. Navigate to Agent Load screen while tasks are running
2. Observe the display

**Expected Results**:
- ✅ Busy agents have status dot as "busy" (green/pulsing)
- ✅ Current Task shows task ID (e.g., "T001")
- ✅ Request counts increment as agents work
- ✅ Cost values increase over time
- ✅ Duration increases
- ✅ Token estimates are shown and non-zero
- ✅ Totals row shows correct "Totals (X busy)" where X = number of active agents
- ✅ Active Agents shows "X / N" with green color when X > 0

---

### Test 5: Token Estimation Reasonableness

**Objective**: Verify that token estimates are reasonable for known costs

**Steps**:
1. Find an agent with recent activity and non-zero cost
2. Note the cost_usd value
3. Note the estimated tokens (input/output)
4. Verify calculations manually:
   - Opus: $15/1M input, $75/1M output
   - Sonnet: $3/1M input, $15/1M output
   - Haiku: $0.25/1M input, $1.25/1M output

**Expected Results**:
- ✅ Token estimates are non-zero for non-zero costs
- ✅ Output tokens < Input tokens (typically 60-40 split)
- ✅ Values are in reasonable range (not negative, not billions)
- ✅ Format uses abbreviations: "1.5k", "250k", "1.2M"

**Example Verification**:
- If cost = $0.075 for Opus model
- Estimated: ~600 output tokens, ~2000 input tokens
- Displayed as: "2.0k in / 600 out"

---

### Test 6: Request Count Bar Scaling

**Objective**: Verify that the horizontal bar correctly scales to the max value

**Steps**:
1. Look at multiple agents on the Agent Load screen
2. Find the agent with the most requests
3. Verify that agent's bar is at 100% width
4. Verify other agents' bars are proportionally smaller

**Expected Results**:
- ✅ Agent with max requests has full-width bar
- ✅ Other agents have proportionally smaller bars
- ✅ Agent with 0 requests has no bar (0% width)
- ✅ Bar color is visible and distinct from background

---

### Test 7: Empty State Handling

**Objective**: Verify proper display when no agents exist

**Setup** (for testing only):
1. Temporarily move employees.json
2. Restart server

**Steps**:
1. Navigate to Agent Load screen

**Expected Results**:
- ✅ Shows "No agents found" message
- ✅ No JavaScript errors in console
- ✅ Page remains stable and doesn't crash

**Cleanup**:
- Restore employees.json and restart server

---

### Test 8: Session Total Summary

**Objective**: Verify the summary section displays correct totals

**Steps**:
1. Navigate to Agent Load screen
2. Switch to "Total session" tab
3. Observe the summary boxes below the table

**Expected Results**:
- ✅ "Session Total Cost" shows sum of all agents' total cost
- ✅ "Active Agents" shows "X / N" where X = busy count, N = total
- ✅ "Window Requests" shows total requests for selected window
- ✅ Values update on auto-refresh
- ✅ Cost is highlighted when > $0
- ✅ Active count turns green when > 0

---

### Test 9: Cost Highlighting

**Objective**: Verify high-cost values are visually highlighted

**Steps**:
1. Find or create an agent with cost > $0.50
2. Observe the cost display

**Expected Results**:
- ✅ Cost values > $0.50 have "highlight" class (different color)
- ✅ Lower costs display in normal color
- ✅ Highlighting is consistent across window switches

---

### Test 10: Auto-Refresh Behavior on Tab Change

**Objective**: Verify polling stops when leaving the Agent Load screen

**Steps**:
1. Navigate to Agent Load screen
2. Observe in DevTools Network tab - API calls every 5s
3. Click "Task board" to navigate away
4. Wait 15 seconds
5. Navigate back to Agent Load screen

**Expected Results**:
- ✅ API polling stops when leaving the screen
- ✅ No new /api/agents/metrics calls while on other screens
- ✅ Polling resumes immediately when returning to Agent Load
- ✅ Fresh data is fetched on return

---

## Performance Tests

### Test 11: Large Number of Agents

**Setup**: Configure 10+ agents in employees.json

**Steps**:
1. Navigate to Agent Load screen
2. Observe rendering performance

**Expected Results**:
- ✅ Widget renders within 500ms
- ✅ Auto-refresh remains smooth (no lag)
- ✅ Scrolling (if needed) is smooth
- ✅ No memory leaks over time

---

### Test 12: Network Failure Handling

**Objective**: Verify graceful handling of API failures

**Steps**:
1. Open Agent Load screen
2. Use browser DevTools → Network tab → Throttling → Offline
3. Wait for next refresh attempt (5s)
4. Observe error handling
5. Re-enable network
6. Wait for recovery

**Expected Results**:
- ✅ Shows error message: "Failed to load metrics: [error]"
- ✅ Doesn't crash or freeze
- ✅ Recovers automatically when network returns
- ✅ Error is cleared on successful fetch

---

## Summary Checklist

Before marking T040 as complete, verify:

- [x] Backend tests pass (7/7 in test_t040_agent_load_dashboard.py)
- [ ] Manual Test 1: Auto-refresh works without flicker
- [ ] Manual Test 2: Time window switching works
- [ ] Manual Test 3: Zero active agents display correct
- [ ] Manual Test 4: Multiple active agents display correct
- [ ] Manual Test 5: Token estimation is reasonable
- [ ] Manual Test 6: Request bar scaling is correct
- [ ] Manual Test 7: Empty state handled gracefully
- [ ] Manual Test 8: Session summary displays correctly
- [ ] Manual Test 9: Cost highlighting works
- [ ] Manual Test 10: Polling starts/stops correctly
- [ ] Manual Test 11: Performance with many agents is good
- [ ] Manual Test 12: Network failures handled gracefully

---

## Notes

- All automated backend tests are passing (100%)
- Frontend tests require manual verification as they involve visual rendering and timing
- Consider automated E2E tests with Playwright/Selenium for CI/CD integration in future
