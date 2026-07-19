"""Exhaustive policy evaluator, independent of canonicalization logic."""

from __future__ import annotations

import itertools

import independent_parser


def all_requests():
    return itertools.product(
        independent_parser.PRINCIPALS,
        independent_parser.ACTIONS,
        independent_parser.RESOURCES,
        (False, True),
        independent_parser.HOURS,
        independent_parser.ZONES,
    )


def evaluate(policy: dict, request: tuple) -> str:
    principal, action, resource, mfa, hour, zone = request
    matching = []
    for rule in policy["rules"]:
        mfa_matches = (
            rule["mfa"] == "any"
            or (rule["mfa"] == "required" and mfa is True)
            or (rule["mfa"] == "forbidden" and mfa is False)
        )
        if (
            principal in rule["principals"]
            and action in rule["actions"]
            and resource in rule["resources"]
            and mfa_matches
            and hour in rule["hours"]
            and zone in rule["zones"]
        ):
            matching.append(rule)
    if not matching:
        return policy["default_effect"]
    greatest_priority = max(rule["priority"] for rule in matching)
    retained = [rule for rule in matching if rule["priority"] == greatest_priority]
    return "deny" if any(rule["effect"] == "deny" for rule in retained) else "allow"


def compare_archives(source: bytes, output: bytes) -> dict:
    source_policy = independent_parser.parse_archive(source)
    output_policy = independent_parser.parse_archive(output)
    differing = 0
    first = None
    request_count = 0
    for request in all_requests():
        request_count += 1
        if evaluate(source_policy, request) != evaluate(output_policy, request):
            differing += 1
            if first is None:
                first = request
    if request_count != 1024:
        raise AssertionError(f"expected 1024 requests, got {request_count}")
    return {
        "equivalent": differing == 0,
        "differing_requests": differing,
        "differing_fraction": differing / request_count,
        "first_counterexample": first,
    }

