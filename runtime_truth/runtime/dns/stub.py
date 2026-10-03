"""Minimal authoritative stub DNS server (stdlib only) for Runtime Truth Phase 2.

Serves test-controlled records inside an isolated Docker bridge network so DNS
observations are fully deterministic and never depend on public Internet DNS.

Supported (explicit):
- A records (IPv4), AAAA records (IPv6), single/multi-level CNAME chains.
- NXDOMAIN for names absent from the records file.
- NODATA (NOERROR, zero answers) for known names queried for an unmapped type.
- Query/answer logging as JSON Lines on stdout (one object per query).

Explicitly NOT supported (documented limitation, never silently faked):
- DoH/DoT, DNSSEC validation, EDNS options, zone transfers, dynamic updates.
- Resolver paths that bypass /etc/resolv.conf (hardcoded IPs, DoH clients,
  /etc/hosts entries) are invisible to this observer by design.
- No process attribution: the stub sees source IP/port only, so resulting
  dns_resolution events carry pid=null.

Wire-format notes: names are matched case-insensitively with a trailing dot
stripped; compression pointers in questions are not expected from libc
resolvers and raise a clean error for that packet only.
"""

import argparse
import json
import socket
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

QTYPE_NAMES = {1: "A", 28: "AAAA", 5: "CNAME", 255: "ANY"}
QTYPE_CODES = {"A": 1, "AAAA": 28, "CNAME": 5, "ANY": 255}

DEFAULT_TTL = 60


def load_records(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load {hostname: {"A": [...], "AAAA": [...], "CNAME": [...]}} normalized lowercase."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    records: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, dict):
        for name, entry in raw.items():
            if isinstance(entry, dict):
                records[str(name).strip().lower().rstrip(".")] = entry
    return records


def decode_name(pkt: bytes, off: int) -> Tuple[str, int]:
    labels: List[str] = []
    jumped = False
    original_off = off
    seen: set = set()
    while True:
        if off >= len(pkt):
            raise ValueError("truncated question name")
        length = pkt[off]
        if length == 0:
            off += 1
            break
        if length & 0xC0:
            if not jumped:
                original_off = off + 2
            if off + 1 >= len(pkt):
                raise ValueError("truncated compression pointer")
            off = ((length & 0x3F) << 8) | pkt[off + 1]
            if off in seen:
                raise ValueError("compression loop")
            seen.add(off)
            jumped = True
            continue
        off += 1
        if off + length > len(pkt):
            raise ValueError("truncated label")
        labels.append(pkt[off:off + length].decode("ascii", "replace"))
        off += length
    return ".".join(labels), (original_off if jumped else off)


def encode_name(name: str) -> bytes:
    out = b""
    for part in name.split("."):
        encoded = part.encode("ascii", "replace")
        out += struct.pack("B", len(encoded)) + encoded
    return out + b"\x00"


class StubDnsServer:
    """Authoritative stub server for a fixed record set."""

    def __init__(
        self,
        records: Dict[str, Dict[str, Any]],
        bind_host: str = "0.0.0.0",
        bind_port: int = 53,
        default_ttl: int = DEFAULT_TTL,
    ):
        self.records = records
        self.bind_host = bind_host
        self.bind_port = bind_port
        self.default_ttl = default_ttl
        self.sock: Optional[socket.socket] = None

    def resolve(
        self, qname: str, qtype: int
    ) -> Tuple[List[str], List[str], int, List[Dict[str, Any]]]:
        """Return (answers, cname_chain, rcode, answer_details).

        rcode: 0 NOERROR, 3 NXDOMAIN. NODATA is NOERROR with zero answers.
        """
        name = qname.lower().rstrip(".")
        chain: List[str] = []
        visited: set = set()
        current = name
        while True:
            if current in visited:
                return [], chain, 2, []  # SERVFAIL on CNAME loop
            visited.add(current)
            entry = self.records.get(current)
            if entry is None:
                if chain:
                    return [], chain, 3, []  # dangling CNAME target
                return [], [], 3, []  # NXDOMAIN
            ttl = int(entry.get("ttl", self.default_ttl))
            if qtype == 255:  # ANY: return everything known
                details: List[Dict[str, Any]] = []
                for cname in entry.get("CNAME", []) or []:
                    details.append({"type": "CNAME", "value": cname, "ttl": ttl})
                for ip in entry.get("A", []) or []:
                    details.append({"type": "A", "value": ip, "ttl": ttl})
                for ip6 in entry.get("AAAA", []) or []:
                    details.append({"type": "AAAA", "value": ip6, "ttl": ttl})
                answers = [d["value"] for d in details if d["type"] in ("A", "AAAA")]
                return answers, chain, 0, details
            if qtype == 1:
                ips = list(entry.get("A", []) or [])
                if ips:
                    return ips, chain, 0, [{"type": "A", "value": ip, "ttl": ttl} for ip in ips]
                if "CNAME" in entry and entry["CNAME"]:
                    target = str(entry["CNAME"][0])
                    chain.append(target)
                    current = target.lower().rstrip(".")
                    continue
                # Known name, no A records: NODATA if the name exists at all
                has_any = bool(entry.get("AAAA") or entry.get("CNAME"))
                return [], chain, 0 if (has_any or chain) else 3, []
            if qtype == 28:
                ips6 = list(entry.get("AAAA", []) or [])
                if ips6:
                    return ips6, chain, 0, [{"type": "AAAA", "value": ip, "ttl": ttl} for ip in ips6]
                if "CNAME" in entry and entry["CNAME"]:
                    target = str(entry["CNAME"][0])
                    chain.append(target)
                    current = target.lower().rstrip(".")
                    continue
                has_any = bool(entry.get("A") or entry.get("CNAME"))
                return [], chain, 0 if (has_any or chain) else 3, []
            # Other types: NODATA for known names, NXDOMAIN otherwise
            return [], chain, 0, []

    def build_response(
        self, query: bytes, qname: str, qtype: int, answers: List[str],
        chain: List[str], rcode: int, details: List[Dict[str, Any]],
    ) -> bytes:
        txid = struct.unpack(">H", query[:2])[0]
        qdcount = 1
        header_flags = 0x8180 if rcode == 0 else 0x8180 | rcode
        question_end = self._question_end(query)
        response = struct.pack(">HHHHHH", txid, header_flags, qdcount, 0, 0, 0)
        response += query[12:question_end]
        ancount = 0
        owner = encode_name(qname)
        for target in chain:
            response += owner + struct.pack(">HHIH", 5, 1, self.default_ttl, len(encode_name(target)))
            response += encode_name(target)
            ancount += 1
            owner = encode_name(target)
        for detail in details:
            rtype = detail["type"]
            ttl = int(detail.get("ttl", self.default_ttl))
            if rtype == "A":
                response += owner + struct.pack(">HHIH", 1, 1, ttl, 4) + socket.inet_aton(detail["value"])
                ancount += 1
            elif rtype == "AAAA":
                response += owner + struct.pack(">HHIH", 28, 1, ttl, 16) + socket.inet_pton(socket.AF_INET6, detail["value"])
                ancount += 1
        header = struct.pack(">HHHHHH", txid, header_flags, qdcount, ancount, 0, 0)
        return header + response[12:]

    @staticmethod
    def _question_end(query: bytes) -> int:
        _, off = decode_name(query, 12)
        return off + 4

    def handle_packet(self, data: bytes, client: Tuple[str, int]) -> Optional[Dict[str, Any]]:
        """Process one datagram; returns the log record (also sent on the wire)."""
        ts = datetime.now(timezone.utc).isoformat()
        try:
            if len(data) < 12:
                return None
            _, _, qdcount, _, _, _ = struct.unpack(">HHHHHH", data[:12])
            if qdcount != 1:
                return None
            qname, off = decode_name(data, 12)
            qtype, _ = struct.unpack(">HH", data[off:off + 4])
        except (ValueError, struct.error):
            return None
        answers, chain, rcode, details = self.resolve(qname, qtype)
        try:
            response = self.build_response(data, qname, qtype, answers, chain, rcode, details)
            assert self.sock is not None
            self.sock.sendto(response, client)
        except (OSError, ValueError, struct.error, AssertionError):
            pass
        return {
            "ts": ts,
            "client": client[0],
            "query_name": qname.lower().rstrip("."),
            "query_type": QTYPE_NAMES.get(qtype, str(qtype)),
            "answers": answers,
            "cname_chain": chain,
            "rcode": {0: "NOERROR", 2: "SERVFAIL", 3: "NXDOMAIN"}.get(rcode, str(rcode)),
            "ttl": self.default_ttl,
        }

    def serve(self, duration_seconds: float = 60.0) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.bind_host, self.bind_port))
        self.sock.settimeout(1.0)
        print("READY", flush=True)
        deadline = time.time() + duration_seconds
        while time.time() < deadline:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            record = self.handle_packet(data, addr)
            if record is not None:
                print(json.dumps(record), flush=True)
        self.sock.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Runtime Truth deterministic stub DNS server")
    parser.add_argument("--records", default="/dns/records.json")
    parser.add_argument("--port", type=int, default=53)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL)
    args = parser.parse_args(argv)
    records = load_records(Path(args.records))
    StubDnsServer(records, bind_port=args.port, default_ttl=args.ttl).serve(args.duration)
    return 0


if __name__ == "__main__":
    sys.exit(main())
