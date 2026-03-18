"""Shared pytest fixtures for qa-UScomparer tests."""

import pytest


@pytest.fixture
def sample_issue_a() -> dict:
    return {
        "key":              "PROJ-101",
        "id":               "10001",
        "self":             "https://org.atlassian.net/rest/api/3/issue/10001",
        "summary":          "Login button not working on mobile",
        "issuetype":        "Bug",
        "status":           "In Progress",
        "priority":         "High",
        "assignee":         "John Doe",
        "reporter":         "Jane Smith",
        "labels":           ["mobile", "login"],
        "components":       ["Frontend"],
        "fixVersions":      ["2.3.0"],
        "versions":         ["2.1.0"],
        "description":      "The login button does not respond on iOS devices.",
        "customfield_10016": 3,
        "duedate":          "2026-04-01",
        "created":          "2026-03-01T10:00:00.000Z",
        "updated":          "2026-03-10T12:00:00.000Z",
        "project":          "PROJ",
        "resolution":       None,
        "environment":      "iOS 17 / Safari",
    }


@pytest.fixture
def sample_issue_b() -> dict:
    return {
        "key":              "PROJ-102",
        "id":               "10002",
        "self":             "https://org.atlassian.net/rest/api/3/issue/10002",
        "summary":          "Login button not working on Android",
        "issuetype":        "Bug",
        "status":           "Open",
        "priority":         "Medium",
        "assignee":         "John Doe",
        "reporter":         "Bob Wilson",
        "labels":           ["mobile", "android"],
        "components":       ["Frontend", "Mobile"],
        "fixVersions":      ["2.3.0"],
        "versions":         ["2.2.0"],
        "description":      "The login button does not respond on Android devices.",
        "customfield_10016": 5,
        "duedate":          "2026-04-15",
        "created":          "2026-03-05T09:00:00.000Z",
        "updated":          "2026-03-12T15:00:00.000Z",
        "project":          "PROJ",
        "resolution":       None,
        "environment":      "Android 14 / Chrome",
    }
