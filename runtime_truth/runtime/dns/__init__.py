"""Controlled stub DNS server for deterministic network-identity observation."""

from runtime_truth.runtime.dns.stub import StubDnsServer, load_records

__all__ = ["StubDnsServer", "load_records"]
