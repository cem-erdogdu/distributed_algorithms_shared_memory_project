from process import Process
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


class Timestamp:
    """Timestamp with writer ID for unique ordering across multiple writers.

    Comparison uses (timestamp, writer_id) tuple - higher timestamp wins,
    and for equal timestamps, higher writer_id wins.
    """

    def __init__(self, ts=0, writer_id=""):
        self.ts = ts
        self.writer_id = writer_id

    def __repr__(self):
        return f"({self.ts}, {self.writer_id})"

    def __eq__(self, other):
        if not isinstance(other, Timestamp):
            return False
        return (self.ts, self.writer_id) == (other.ts, other.writer_id)

    def __lt__(self, other):
        return (self.ts, self.writer_id) < (other.ts, other.writer_id)

    def __le__(self, other):
        return (self.ts, self.writer_id) <= (other.ts, other.writer_id)

    def __gt__(self, other):
        return (self.ts, self.writer_id) > (other.ts, other.writer_id)

    def __ge__(self, other):
        return (self.ts, self.writer_id) >= (other.ts, other.writer_id)


class RegisterValue:
    """Represents a value stored in the register with timestamp and writer ID."""

    def __init__(self, value=None, timestamp=None):
        self.value = value
        self.timestamp = timestamp or Timestamp(0, "")

    def __repr__(self):
        return f"RegisterValue(value={self.value}, ts={self.timestamp})"


class RegisterProcess(Process):
    """A unified process that can both read and write to the atomic register.

    Each process stores a timestamp-value pair and handles both READ and WRITE messages.

    Write operation has two phases:
    Phase 1: Read current timestamps from majority, pick highest
    Phase 2: Increment timestamp, broadcast write, wait for majority ACKs

    Read operation has two phases:
    Phase 1: Broadcast READ_REQ, collect majority responses, pick highest timestamp value
    Phase 2: Write-back that value to all processes, wait for majority ACKs, then return
    """

    def __init__(self, proc_id):
        super().__init__(proc_id)
        self.stored = RegisterValue(None, Timestamp(0, ""))

        # Configuration
        self.process_ids = []
        self.majority = 0

        # Operation state
        self.operation = None  # None, "read", "write"
        self.phase = None  # None, "read", "writeback" (for reads), "read", "write" (for writes)
        self._was_writeback = False  # Track if completed phase was writeback

        # Phase 1 state: collecting read responses
        self.pending_read_responses = set()
        self.collected = []
        self.read_phase_participants = set()  # Processes that responded in read phase

        # Phase 2 state: write/writeback
        self.pending_write_acks = set()
        self.write_ack_count = 0
        self.value_to_write = None
        self.write_phase_participants = set()  # Processes that ACKed in write phase

        # Last operation tracking for visualization
        self.last_role = None  # "writer", "reader", "replica", None
        self.last_participated = False  # Was this process part of a majority?

        # Callbacks
        self.on_read_done = None
        self.on_write_done = None

    def read(self, process_ids, callback=None):
        """Start a two-phase read operation."""
        self._init_operation(process_ids, "read", callback)
        self._start_phase_read()

    def write(self, value, process_ids, callback=None):
        """Start a two-phase write operation."""
        self._init_operation(process_ids, "write", callback)
        self.value_to_write = value
        self._start_phase_read()

    def _init_operation(self, process_ids, operation, callback):
        """Initialize common state for read or write operation."""
        self.process_ids = list(process_ids)
        self.majority = (len(process_ids) // 2) + 1
        self.operation = operation
        self.on_read_done = callback if operation == "read" else None
        self.on_write_done = callback if operation == "write" else None
        self.read_phase_participants = set()
        self.write_phase_participants = set()

    def _start_phase_read(self):
        """Phase 1 for both read and write: Broadcast READ_REQ to all processes."""
        self.phase = "read"
        self.pending_read_responses = set(self.process_ids)
        self.collected = []
        for pid in self.process_ids:
            self.send(pid, "READ_REQ")

    def _start_phase_writeback(self, value):
        """Phase 2 for read: Write-back the highest timestamp value to all processes."""
        self._was_writeback = True
        self.phase = "writeback"
        self.value_to_write = value
        self.pending_write_acks = set(self.process_ids)
        self.write_ack_count = 0
        for pid in self.process_ids:
            self.send(pid, "WRITE", {
                "value": value.value,
                "timestamp_ts": value.timestamp.ts,
                "timestamp_writer": value.timestamp.writer_id
            })

    def _start_phase_write(self, value, new_timestamp):
        """Phase 2 for write: Broadcast the new value with incremented timestamp."""
        self._was_writeback = False
        self.phase = "write"
        self.value_to_write = RegisterValue(value, new_timestamp)
        self.pending_write_acks = set(self.process_ids)
        self.write_ack_count = 0
        for pid in self.process_ids:
            self.send(pid, "WRITE", {
                "value": value,
                "timestamp_ts": new_timestamp.ts,
                "timestamp_writer": new_timestamp.writer_id
            })

    def on_message(self, message):
        # Handle incoming WRITE messages (for replica functionality)
        if message.msg_type == "WRITE":
            incoming_ts = Timestamp(
                message.payload["timestamp_ts"],
                message.payload["timestamp_writer"]
            )
            if incoming_ts > self.stored.timestamp:
                self.stored = RegisterValue(message.payload["value"], incoming_ts)
            self.send(message.sender, "ACK")
            # Track that this process acted as a replica
            self.last_role = "replica"
            self.last_participated = True
            return

        # Handle incoming READ_REQ messages (for replica functionality)
        if message.msg_type == "READ_REQ":
            self.send(message.sender, "READ_RESP", {
                "value": self.stored.value,
                "timestamp_ts": self.stored.timestamp.ts,
                "timestamp_writer": self.stored.timestamp.writer_id
            })
            # Track that this process acted as a replica
            self.last_role = "replica"
            self.last_participated = True
            return

        # Handle READ_RESP for ongoing operations
        if self.phase == "read" and message.msg_type == "READ_RESP":
            if message.sender in self.pending_read_responses:
                self.pending_read_responses.remove(message.sender)
                self.read_phase_participants.add(message.sender)
                self.collected.append(RegisterValue(
                    message.payload["value"],
                    Timestamp(message.payload["timestamp_ts"], message.payload["timestamp_writer"])
                ))
                if len(self.collected) >= self.majority:
                    # Phase 1 complete - pick highest timestamp value
                    best = max(self.collected, key=lambda rv: rv.timestamp)
                    if self.operation == "read":
                        # Start Phase 2: write-back
                        self._start_phase_writeback(best)
                    elif self.operation == "write":
                        # Compute new timestamp and start Phase 2: write
                        new_ts = Timestamp(best.timestamp.ts + 1, self.proc_id)
                        self._start_phase_write(self.value_to_write, new_ts)

        # Handle ACK for write/writeback phase
        elif self.phase in ("writeback", "write") and message.msg_type == "ACK":
            if message.sender in self.pending_write_acks:
                self.pending_write_acks.remove(message.sender)
                self.write_phase_participants.add(message.sender)
                self.write_ack_count += 1
                if self.write_ack_count >= self.majority:
                    # Operation complete
                    self.operation = None
                    self.phase = None
                    # Set role based on operation type
                    if self._was_writeback:
                        self.last_role = "reader"
                    else:
                        self.last_role = "writer"
                    self.last_participated = True
                    if self._was_writeback:
                        if self.on_read_done:
                            self.on_read_done(self.value_to_write)
                    else:
                        if self.on_write_done:
                            self.on_write_done(self.value_to_write)

    def is_busy(self):
        """Return True if an operation is in progress."""
        return self.operation is not None

    def is_reading(self):
        return self.operation == "read"

    def is_writing(self):
        return self.operation == "write"

    def get_phase(self):
        """Return current phase for debugging/logging."""
        return self.phase

    def get_all_participants(self):
        """Get all processes that participated in the last operation."""
        return self.read_phase_participants | self.write_phase_participants


def print_state_table(processes, completed_pid=None, participants=None, tick=0, operation_type=None):
    """Print a Rich table showing the state of all processes.

    Args:
        processes: List of RegisterProcess objects
        completed_pid: PID of the process that just completed an operation (green)
        participants: Set of PIDs that participated in the majority (yellow)
        tick: Current simulation tick
        operation_type: Type of operation that just completed
    """
    if participants is None:
        participants = set()

    table = Table(title=f"Process State at Tick {tick}" + (f" (after {operation_type})" if operation_type else ""))
    table.add_column("PID", style="bold")
    table.add_column("Value")
    table.add_column("Timestamp")
    table.add_column("Writer ID")
    table.add_column("Last Role")
    table.add_column("Status")

    for p in processes:
        # Determine styling
        if p.crashed:
            pid_text = Text(p.proc_id, style="red strike")
            value_text = Text(str(p.stored.value), style="red strike")
            ts_text = Text(str(p.stored.timestamp.ts), style="red strike")
            writer_text = Text(str(p.stored.timestamp.writer_id), style="red strike")
            role_text = Text("CRASHED", style="red strike")
            status_text = Text("CRASHED", style="red strike")
        elif p.proc_id == completed_pid:
            pid_text = Text(p.proc_id, style="bold green")
            value_text = Text(str(p.stored.value), style="green")
            ts_text = Text(str(p.stored.timestamp.ts), style="green")
            writer_text = Text(str(p.stored.timestamp.writer_id), style="green")
            role_text = Text(p.last_role or "-", style="green")
            status_text = Text("COMPLETED", style="green")
        elif p.proc_id in participants:
            pid_text = Text(p.proc_id, style="yellow")
            value_text = Text(str(p.stored.value), style="yellow")
            ts_text = Text(str(p.stored.timestamp.ts), style="yellow")
            writer_text = Text(str(p.stored.timestamp.writer_id), style="yellow")
            role_text = Text(p.last_role or "-", style="yellow")
            status_text = Text("PARTICIPANT", style="yellow")
        else:
            pid_text = Text(p.proc_id)
            value_text = Text(str(p.stored.value))
            ts_text = Text(str(p.stored.timestamp.ts))
            writer_text = Text(str(p.stored.timestamp.writer_id))
            role_text = Text(p.last_role or "-")
            status_text = Text("idle")

        table.add_row(pid_text, value_text, ts_text, writer_text, role_text, status_text)

    console.print(table)
    console.print()
