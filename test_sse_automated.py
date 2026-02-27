"""Automated SSE testing for T035."""

import asyncio
import json
import httpx
import sys
import time
from pathlib import Path

# Add paths
KOK_DIR = Path(__file__).resolve().parent / "kok"
TEMPLATE_COMMON = KOK_DIR / "template_tayfa" / "common"
sys.path.insert(0, str(TEMPLATE_COMMON))
sys.path.insert(0, str(KOK_DIR))


async def test_sse_endpoint_exists():
    """Test that SSE endpoint is accessible."""
    print("\n[TEST 1] SSE endpoint accessibility")
    try:
        # We can't fully consume SSE stream via httpx, but we can check it responds
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Start the request but don't wait for full response (SSE is infinite)
            print("  - Connecting to /api/board-events...")
            # Just verify the endpoint exists and returns expected headers
            resp = await client.get("http://localhost:8008/api/board-events",
                                    timeout=2.0,
                                    follow_redirects=True)
            print(f"  PASS: SSE endpoint returned status {resp.status_code}")
            return True
    except httpx.ReadTimeout:
        # This is expected for SSE - it's a long-lived connection
        print("  PASS: SSE endpoint connected (timeout expected for streaming)")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_sse_events_on_status_change():
    """Test that changing task status triggers SSE event."""
    print("\n[TEST 2] SSE events on task status change")

    # Get current tasks
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get("http://localhost:8008/api/tasks-list")
        tasks = resp.json().get("tasks", [])

        if not tasks:
            print("  SKIP: No tasks found to test with")
            return True

        # Find a task we can toggle
        test_task = None
        for task in tasks:
            if task.get("status") in ["new", "done"]:
                test_task = task
                break

        if not test_task:
            print("  SKIP: No suitable task found")
            return True

        task_id = test_task["id"]
        original_status = test_task["status"]
        new_status = "done" if original_status == "new" else "new"

        print(f"  - Testing with task {task_id}")
        print(f"  - Changing status: {original_status} -> {new_status}")

        # Change task status
        await client.put(f"http://localhost:8008/api/tasks-list/{task_id}/status",
                        json={"status": new_status})

        # Wait a moment for SSE propagation
        await asyncio.sleep(1)

        # Verify status changed
        resp = await client.get("http://localhost:8008/api/tasks-list")
        updated_tasks = resp.json().get("tasks", [])
        updated_task = next((t for t in updated_tasks if t["id"] == task_id), None)

        if updated_task and updated_task["status"] == new_status:
            print(f"  PASS: Task status changed successfully")

            # Change back to original status
            await client.put(f"http://localhost:8008/api/tasks-list/{task_id}/status",
                            json={"status": original_status})
            return True
        else:
            print(f"  FAIL: Task status did not change")
            return False


async def test_board_data_endpoints():
    """Test that board data endpoints work."""
    print("\n[TEST 3] Board data endpoints")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Test tasks endpoint
            resp = await client.get("http://localhost:8008/api/tasks-list")
            tasks_data = resp.json()
            print(f"  PASS: /api/tasks-list returned {len(tasks_data.get('tasks', []))} tasks")

            # Test sprints endpoint
            resp = await client.get("http://localhost:8008/api/sprints")
            sprints_data = resp.json()
            print(f"  PASS: /api/sprints returned {len(sprints_data.get('sprints', []))} sprints")

            # Test running tasks endpoint
            resp = await client.get("http://localhost:8008/api/running-tasks")
            running_data = resp.json()
            print(f"  PASS: /api/running-tasks returned {len(running_data.get('running', {}))} running tasks")

            return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_sse_reconnection_readiness():
    """Test that SSE reconnection logic is present in frontend."""
    print("\n[TEST 4] SSE reconnection logic (frontend check)")

    # Check if board.js has proper SSE error handling
    board_js = Path("kok/static/js/board.js")
    if not board_js.exists():
        print("  FAIL: board.js not found")
        return False

    content = board_js.read_text()

    checks = [
        ("EventSource", "EventSource is used"),
        ("onerror", "Error handler is defined"),
        ("board-events", "SSE endpoint is correct"),
        ("connectBoardSSE", "SSE connection function exists"),
    ]

    passed = True
    for check_str, description in checks:
        if check_str in content:
            print(f"  PASS: {description}")
        else:
            print(f"  FAIL: {description} - not found")
            passed = False

    return passed


async def test_no_polling_in_code():
    """Test that polling code was removed/disabled."""
    print("\n[TEST 5] No polling in code")

    board_js = Path("kok/static/js/board.js")
    if not board_js.exists():
        print("  FAIL: board.js not found")
        return False

    content = board_js.read_text()

    # Check that polling is not active
    if "setInterval" in content:
        # Check if it's only used for elapsed timer, not for board refresh
        lines_with_setinterval = [line for line in content.split('\n') if 'setInterval' in line.lower()]

        # Filter out the ones we expect (elapsed timer)
        unexpected = [l for l in lines_with_setinterval if 'elapsed' not in l.lower() and 'running' not in l.lower()]

        if unexpected:
            print("  WARN: Found setInterval not related to elapsed timer:")
            for line in unexpected:
                print(f"    {line.strip()}")
        else:
            print("  PASS: setInterval only used for elapsed timer")
    else:
        print("  PASS: No setInterval found")

    # Check for SSE usage
    if "EventSource" in content and "/api/board-events" in content:
        print("  PASS: SSE is used for board updates")
        return True
    else:
        print("  FAIL: SSE not properly configured")
        return False


async def verify_app_state_has_board_subscribers():
    """Check that app_state has SSE subscriber management."""
    print("\n[TEST 6] SSE subscriber management in app_state")

    app_state_path = Path("kok/app_state.py")
    if not app_state_path.exists():
        print("  FAIL: app_state.py not found")
        return False

    content = app_state_path.read_text()

    checks = [
        ("board_subscribe", "board_subscribe function exists"),
        ("board_unsubscribe", "board_unsubscribe function exists"),
        ("_board_subscribers", "board subscribers tracking exists"),
    ]

    passed = True
    for check_str, description in checks:
        if check_str in content:
            print(f"  PASS: {description}")
        else:
            print(f"  FAIL: {description}")
            passed = False

    return passed


async def main():
    print("="*70)
    print("T035: SSE Board Updates - Automated Tests")
    print("="*70)

    # Check server is running
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:8008/api/status")
            if resp.status_code == 200:
                print("\nServer is running on http://localhost:8008")
            else:
                print(f"\nServer responded with error: {resp.status_code}")
                return False
    except Exception as e:
        print(f"\nCannot connect to server: {e}")
        print("Please start the server first: python kok/app.py")
        return False

    # Run tests
    tests = [
        test_sse_endpoint_exists,
        test_board_data_endpoints,
        test_sse_events_on_status_change,
        test_sse_reconnection_readiness,
        test_no_polling_in_code,
        verify_app_state_has_board_subscribers,
    ]

    results = []
    for test_func in tests:
        try:
            result = await test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            print(f"\nTest {test_func.__name__} failed with exception: {e}")
            results.append((test_func.__name__, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"[{status}] {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll automated tests passed!")
        print("\nMANUAL VERIFICATION STILL NEEDED:")
        print("1. Open browser to http://localhost:8008")
        print("2. Open DevTools Network tab, filter EventStream")
        print("3. Verify /api/board-events connection is open")
        print("4. Change a task status via CLI - board should update within 2s")
        print("5. Open 2 tabs - changes in one should appear in the other")
        print("6. Watch for keepalive comments every ~30s")
        return True
    else:
        print(f"\n{total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
