#!/usr/bin/env python3
"""
Minimal test for the realm registry backend.
Tests basic CRUD operations on the realm registry using ORM.
"""

import sys
import time
from unittest.mock import MagicMock

import _cdk as basilisk

mock_ic = basilisk.ic

from realm_registry_backend.api.credits import (
    add_user_credits,
    deduct_user_credits,
    get_billing_status,
    get_user_credits,
)
from realm_registry_backend.api.registry import (
    count_registered_realms,
    get_registered_realm,
    list_registered_realms,
    register_realm_by_caller,
    remove_registered_realm,
)
from realm_registry_backend.api.status import get_status
from realm_registry_backend.core.models import RealmRecord, SlugRecord, UserCredits

# Color formatting for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_success(message):
    print(f"{GREEN}✓ {message}{RESET}")


def print_failure(message, error=None):
    print(f"{RED}✗ {message}{RESET}")
    if error:
        print(f"  Error: {error}")


def clear_database():
    """Clear all realm records from the database"""
    try:
        for slug in list(SlugRecord.instances()):
            slug.delete()
        all_realms = list(RealmRecord.instances())
        for realm in all_realms:
            realm.delete()
    except Exception:
        pass


def add_test_realm(realm_id: str, name: str, url: str = ""):
    """Helper to add a realm using register_realm_by_caller with mocked caller"""
    mock_ic.caller.return_value = realm_id
    return register_realm_by_caller(name, url)


def clear_user_credits():
    """Clear all user credits from the database"""
    try:
        all_credits = list(UserCredits.instances())
        for credit in all_credits:
            credit.delete()
    except Exception:
        pass


def test_register_realm():
    """Test registering a realm with the registry"""
    try:
        clear_database()

        # Test registering a valid realm
        result = add_test_realm("test-realm-1", "Test Realm 1", "https://test1.com")
        assert result["success"], f"Failed to register realm: {result.get('error')}"
        assert "test-realm-1" in result["message"]

        # Test updating existing realm (upsert behavior)
        result = add_test_realm("test-realm-1", "Test Realm 1 Updated", "https://test1-updated.com")
        assert result["success"], "Should allow updating existing realm"
        assert "updated" in result.get("message", "").lower()

        # Test registering realm with empty name
        result = add_test_realm("test-realm-2", "", "https://test.com")
        assert not result["success"], "Should not allow empty realm name"
        assert "cannot be empty" in result["error"]

        print_success("register_realm tests passed")
        return True
    except Exception as e:
        print_failure("register_realm tests failed", str(e))
        return False


def test_get_realm():
    """Test getting a realm from the registry"""
    try:
        clear_database()

        # Add a test realm
        add_test_realm("test-realm-1", "Test Realm 1", "https://test1.com")

        # Test getting existing realm
        result = get_registered_realm("test-realm-1")
        assert result["success"], f"Failed to get realm: {result.get('error')}"
        assert result["realm"]["id"] == "test-realm-1"
        assert result["realm"]["name"] == "Test Realm 1"
        assert result["realm"]["url"] == "https://test1.com"

        # Test getting non-existent realm
        result = get_registered_realm("non-existent")
        assert not result["success"], "Should return error for non-existent realm"
        assert "not found" in result["error"]

        print_success("get_realm tests passed")
        return True
    except Exception as e:
        print_failure("get_realm tests failed", str(e))
        return False


def test_list_realms():
    """Test listing all realms"""
    try:
        clear_database()

        # Test with empty registry
        realms = list_registered_realms()
        assert len(realms) == 0, "Should return empty list for empty registry"

        # Add multiple realms
        add_test_realm("test-realm-1", "Test Realm 1", "https://test1.com")
        add_test_realm("test-realm-2", "Test Realm 2", "https://test2.com")
        add_test_realm("test-realm-3", "Test Realm 3", "https://test3.com")

        # Test listing all realms
        realms = list_registered_realms()
        assert len(realms) == 3, f"Expected 3 realms, got {len(realms)}"

        print_success("list_realms tests passed")
        return True
    except Exception as e:
        print_failure("list_realms tests failed", str(e))
        return False


def test_remove_realm():
    """Test removing a realm from the registry"""
    try:
        clear_database()

        # Add a test realm
        add_test_realm("test-realm-1", "Test Realm 1", "https://test1.com")

        # Test removing existing realm
        result = remove_registered_realm("test-realm-1")
        assert result["success"], f"Failed to remove realm: {result.get('error')}"

        # Verify realm was removed
        result = get_registered_realm("test-realm-1")
        assert not result["success"], "Realm should not exist after removal"

        # Test removing non-existent realm
        result = remove_registered_realm("non-existent")
        assert not result["success"], "Should return error for non-existent realm"
        assert "not found" in result["error"]

        print_success("remove_realm tests passed")
        return True
    except Exception as e:
        print_failure("remove_realm tests failed", str(e))
        return False


def test_remove_realm_cleans_slugs():
    """Removing a realm also deletes federation slug records."""
    try:
        clear_database()
        backend_id = "backend-canister-1"
        add_test_realm(backend_id, "Slug Realm", "https://slug.example")

        SlugRecord(
            slug="slug-realm",
            realm_id=backend_id,
            frontend_canister_id="fe-canister",
            claimed_by=backend_id,
            claimed_at=time.time(),
        )

        result = remove_registered_realm(backend_id)
        assert result["success"], result.get("error")
        assert SlugRecord["slug-realm"] is None

        print_success("remove_realm slug cleanup tests passed")
        return True
    except Exception as e:
        print_failure("remove_realm slug cleanup tests failed", str(e))
        return False


def test_count_realms():
    """Test counting realms"""
    try:
        clear_database()

        # Test empty registry
        count = count_registered_realms()
        assert count == 0, f"Expected 0 realms, got {count}"

        # Add realms
        add_test_realm("test-realm-1", "Test Realm 1", "https://test1.com")
        add_test_realm("test-realm-2", "Test Realm 2", "https://test2.com")

        # Test count
        count = count_registered_realms()
        assert count == 2, f"Expected 2 realms, got {count}"

        # Remove a realm
        remove_registered_realm("test-realm-1")

        # Test count after removal
        count = count_registered_realms()
        assert count == 1, f"Expected 1 realm after removal, got {count}"

        print_success("count_realms tests passed")
        return True
    except Exception as e:
        print_failure("count_realms tests failed", str(e))
        return False


def test_status():
    """Test getting registry status"""
    try:
        clear_database()

        # Test status with empty registry
        status = get_status()
        assert status["status"] == "ok", f"Expected status 'ok', got {status['status']}"
        assert "version" in status, "Status should contain 'version'"
        assert "commit" in status, "Status should contain 'commit'"
        assert "commit_datetime" in status, "Status should contain 'commit_datetime'"
        assert "realms_count" in status, "Status should contain 'realms_count'"
        assert status["realms_count"] == 0, f"Expected 0 realms, got {status['realms_count']}"

        # Add some realms and check count is updated
        add_test_realm("test-realm-1", "Test Realm 1", "https://test1.com")
        add_test_realm("test-realm-2", "Test Realm 2", "https://test2.com")

        status = get_status()
        assert status["realms_count"] == 2, f"Expected 2 realms, got {status['realms_count']}"

        # Verify version/commit fields are present and non-empty
        # (placeholders are replaced by CI sed commands before tests run)
        assert status["version"], "version should be non-empty"
        assert status["commit"], "commit should be non-empty"
        assert status["commit_datetime"], "commit_datetime should be non-empty"

        print_success("status tests passed")
        return True
    except Exception as e:
        print_failure("status tests failed", str(e))
        return False


def test_billing_status():
    """Test billing status and credits functionality"""
    try:
        clear_user_credits()

        # Test billing status with no users
        result = get_billing_status()
        assert result["success"], f"Failed to get billing status: {result.get('error')}"
        assert result["billing"]["users_count"] == 0, f"Expected 0 users, got {result['billing']['users_count']}"
        assert result["billing"]["total_balance"] == 0, f"Expected 0 balance, got {result['billing']['total_balance']}"
        assert result["billing"]["total_purchased"] == 0, f"Expected 0 purchased, got {result['billing']['total_purchased']}"
        assert result["billing"]["total_spent"] == 0, f"Expected 0 spent, got {result['billing']['total_spent']}"

        # Add credits to a user
        add_result = add_user_credits("user-1", 100, description="Test top-up")
        assert add_result["success"], f"Failed to add credits: {add_result.get('error')}"
        assert add_result["credits"]["balance"] == 100

        # Check billing status with one user
        result = get_billing_status()
        assert result["billing"]["users_count"] == 1, f"Expected 1 user, got {result['billing']['users_count']}"
        assert result["billing"]["total_balance"] == 100, f"Expected 100 balance, got {result['billing']['total_balance']}"
        assert result["billing"]["total_purchased"] == 100, f"Expected 100 purchased, got {result['billing']['total_purchased']}"

        # Add credits to another user
        add_result = add_user_credits("user-2", 200, description="Test top-up")
        assert add_result["success"], f"Failed to add credits: {add_result.get('error')}"

        # Check billing status with two users
        result = get_billing_status()
        assert result["billing"]["users_count"] == 2, f"Expected 2 users, got {result['billing']['users_count']}"
        assert result["billing"]["total_balance"] == 300, f"Expected 300 balance, got {result['billing']['total_balance']}"
        assert result["billing"]["total_purchased"] == 300, f"Expected 300 purchased, got {result['billing']['total_purchased']}"

        # Deduct credits from user-1
        deduct_result = deduct_user_credits("user-1", 30, description="Test spend")
        assert deduct_result["success"], f"Failed to deduct credits: {deduct_result.get('error')}"
        assert deduct_result["credits"]["balance"] == 70

        # Check billing status after deduction
        result = get_billing_status()
        assert result["billing"]["total_balance"] == 270, f"Expected 270 balance, got {result['billing']['total_balance']}"
        assert result["billing"]["total_spent"] == 30, f"Expected 30 spent, got {result['billing']['total_spent']}"

        # Test get_user_credits
        user_result = get_user_credits("user-1")
        assert user_result["success"], f"Failed to get user credits: {user_result.get('error')}"
        assert user_result["credits"]["balance"] == 70
        assert user_result["credits"]["total_purchased"] == 100
        assert user_result["credits"]["total_spent"] == 30

        print_success("billing_status tests passed")
        return True
    except Exception as e:
        print_failure("billing_status tests failed", str(e))
        return False


def run_tests():
    """Run all tests and report results"""
    print(f"{BOLD}Running Realm Registry Tests...{RESET}\n")

    # Track test results
    success_count = 0
    failure_count = 0

    # Run tests
    tests = [
        test_register_realm,
        test_get_realm,
        test_list_realms,
        test_remove_realm,
        test_remove_realm_cleans_slugs,
        test_count_realms,
        test_status,
        test_billing_status,
    ]

    for test in tests:
        if test():
            success_count += 1
        else:
            failure_count += 1

    # Print summary
    print(f"\n{BOLD}Test Summary:{RESET}")
    print(f"- {GREEN}{success_count} tests passed{RESET}")
    print(f"- {RED if failure_count > 0 else ''}{failure_count} tests failed{RESET}")

    return failure_count == 0


if __name__ == "__main__":
    # Run the tests
    success = run_tests()

    # Exit with appropriate code
    sys.exit(0 if success else 1)
