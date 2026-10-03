"""Strace log normalizer producing canonical RuntimeEvents."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from runtime_truth.core.enums import RuntimeEventType
from runtime_truth.core.identifiers import generate_event_id
from runtime_truth.core.models import RuntimeEvent
from runtime_truth.observation.base import EventNormalizer
from runtime_truth.runtime.base import RawEvent


class StraceEventNormalizer(EventNormalizer):
    """Parses strace output lines into canonical RuntimeEvents."""

    # Matches prefix: [pid 12345] 12:34:56.789012 or 12345 12:34:56.789012 or 12:34:56.789012
    STRACE_PREFIX_REGEX = re.compile(
        r"^(?:(?:\[pid\s+(\d+)\]|\b(\d+)\b)\s+)?(?:\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+)?([a-zA-Z0-9_]+)\((.*)\)\s*=\s*(.*)$"
    )

    # connect: AF_INET / AF_INET6
    INET4_CONNECT_REGEX = re.compile(
        r'sin_port=htons\((\d+)\),\s*sin_addr=inet_addr\(["\']([^"\']+)["\']\)'
    )
    INET6_CONNECT_REGEX = re.compile(
        r'sin6_port=htons\((\d+)\),\s*sin6_addr=inet_pton\([^,]+,\s*["\']([^"\']+)["\']\)'
    )

    # openat / open: extracts quoted path and flags
    OPENAT_REGEX = re.compile(
        r'(?:AT_FDCWD,\s*)?["\']([^"\']+)["\'](?:,\s*([^,\)]+))?'
    )

    # execve: execve("/path/bin", ["arg0", "arg1", ...], ...)
    EXECVE_REGEX = re.compile(
        r'^["\']([^"\']+)["\'],\s*\[(.*?)\]'
    )

    def normalize(self, raw_event: RawEvent, run_id: str) -> Optional[RuntimeEvent]:
        raw_line = raw_event.raw_payload.strip()
        if not raw_line or "<unfinished" in raw_line or "resumed>" in raw_line:
            return None

        match = self.STRACE_PREFIX_REGEX.match(raw_line)
        if not match:
            return None

        pid_str = match.group(1) or match.group(2)
        pid = int(pid_str) if pid_str else None
        syscall = match.group(3)
        args_str = match.group(4)
        result_str = match.group(5)

        event_type: Optional[RuntimeEventType] = None
        attributes: Dict[str, Any] = {"syscall": syscall, "result": result_str}

        # 1. connect()
        if syscall == "connect":
            inet4 = self.INET4_CONNECT_REGEX.search(args_str)
            if inet4:
                port = int(inet4.group(1))
                dest = inet4.group(2)
                event_type = RuntimeEventType.NETWORK_CONNECT
                attributes["destination"] = dest
                attributes["port"] = port
                attributes["protocol"] = "ipv4"
            else:
                inet6 = self.INET6_CONNECT_REGEX.search(args_str)
                if inet6:
                    port = int(inet6.group(1))
                    dest = inet6.group(2)
                    event_type = RuntimeEventType.NETWORK_CONNECT
                    attributes["destination"] = dest
                    attributes["port"] = port
                    attributes["protocol"] = "ipv6"

        # 2. openat() / open()
        elif syscall in ("openat", "open"):
            open_match = self.OPENAT_REGEX.search(args_str)
            if open_match:
                file_path = open_match.group(1)
                flags = open_match.group(2) or ""
                attributes["path"] = file_path
                attributes["flags"] = flags

                if "O_CREAT" in flags:
                    event_type = RuntimeEventType.FILE_CREATE
                elif any(f in flags for f in ("O_WRONLY", "O_RDWR")):
                    event_type = RuntimeEventType.FILE_WRITE
                else:
                    event_type = RuntimeEventType.FILE_READ

        # 3. unlink() / unlinkat()
        elif syscall in ("unlink", "unlinkat"):
            path_match = re.search(r'["\']([^"\']+)["\']', args_str)
            if path_match:
                event_type = RuntimeEventType.FILE_DELETE
                attributes["path"] = path_match.group(1)

        # 4. execve()
        elif syscall == "execve":
            if result_str.strip().startswith("-1"):
                return None
            exec_match = self.EXECVE_REGEX.search(args_str)
            if exec_match:
                executable = exec_match.group(1)
                raw_args = exec_match.group(2)
                # Parse args
                args = re.findall(r'["\']([^"\']+)["\']', raw_args)
                event_type = RuntimeEventType.PROCESS_SPAWN
                attributes["executable"] = executable
                attributes["args"] = args

        # 5. exit_group() / exit()
        elif syscall in ("exit_group", "exit"):
            event_type = RuntimeEventType.PROCESS_EXIT
            exit_code = re.search(r"(\d+)", args_str)
            attributes["exit_code"] = int(exit_code.group(1)) if exit_code else 0

        if not event_type:
            return None

        event_id = generate_event_id(run_id, raw_line, raw_event.sequence)

        return RuntimeEvent(
            event_id=event_id,
            run_id=run_id,
            timestamp=raw_event.timestamp,
            pid=pid,
            process=attributes.get("executable"),
            event_type=event_type,
            attributes=attributes,
            source=raw_event.collector,
            raw_reference=raw_line,
        )
