import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from network import Network
from register import RegisterProcess, Timestamp, RegisterValue


def run_until_complete(net, processes):
    """Run the network until all processes are idle."""
    while any(p.is_busy() for p in processes if not p.crashed):
        net.step()


def test_non_concurrent_read_returns_last_written_value():
    """
    Test 1: A non-concurrent read should always return the last written value
    and never something older.
    """
    net = Network(latency=2)
    processes = [RegisterProcess(f"P{i}") for i in range(5)]
    process_ids = [f"P{i}" for i in range(5)]
    
    for p in processes:
        net.add_process(p)
    
    results = {}
    
    def on_read_done(pid):
        def callback(value):
            results[pid] = value
        return callback
    
    # Write value 42
    processes[0].write(42, process_ids, lambda v: None)
    run_until_complete(net, processes)
    
    # Write value 99
    processes[1].write(99, process_ids, lambda v: None)
    run_until_complete(net, processes)
    
    # Write value 777
    processes[2].write(777, process_ids, lambda v: None)
    run_until_complete(net, processes)
    
    # Non-concurrent read should return 777
    processes[3].read(process_ids, on_read_done("P3"))
    run_until_complete(net, processes)
    
    assert "P3" in results, "Read should have completed"
    assert results["P3"].value == 777, f"Expected 777, got {results['P3'].value}"
    assert results["P3"].timestamp.ts == 3, f"Expected timestamp 3, got {results['P3'].timestamp.ts}"
    print("Test 1 passed: Non-concurrent read returns last written value")


def test_concurrent_read_returns_only_old_or_new():
    """
    Test 2: A concurrent read must return either the old or the new value
    being written, never an invented value that nobody wrote.
    """
    net = Network(latency=2)
    processes = [RegisterProcess(f"P{i}") for i in range(5)]
    process_ids = [f"P{i}" for i in range(5)]
    
    for p in processes:
        net.add_process(p)
    
    results = {}
    
    def on_read_done(pid):
        def callback(value):
            results[pid] = value
        return callback
    
    # First, write an initial value
    processes[0].write(42, process_ids, lambda v: None)
    run_until_complete(net, processes)
    
    # Start a write of value 99
    processes[1].write(99, process_ids, lambda v: None)
    
    # Immediately start a concurrent read
    processes[2].read(process_ids, on_read_done("P2"))
    
    run_until_complete(net, processes)
    
    # The read should return either 42 (old) or 99 (new), nothing else
    assert "P2" in results, "Read should have completed"
    assert results["P2"].value in [42, 99], \
        f"Concurrent read returned invented value {results['P2'].value}, expected 42 or 99"
    print(f"Test 2 passed: Concurrent read returned {results['P2'].value} (valid: 42 or 99)")


def test_atomic_reads_dont_go_backwards():
    """
    Test 3: Two concurrent reads shouldn't go backwards.
    If one read returns a value with timestamp T, a read that completes
    after it must return a value with timestamp >= T.
    """
    net = Network(latency=2)
    processes = [RegisterProcess(f"P{i}") for i in range(5)]
    process_ids = [f"P{i}" for i in range(5)]
    
    for p in processes:
        net.add_process(p)
    
    results = {}
    completion_order = []
    
    def on_read_done(pid):
        def callback(value):
            results[pid] = value
            completion_order.append(pid)
        return callback
    
    # Write initial value
    processes[0].write(42, process_ids, lambda v: None)
    run_until_complete(net, processes)
    
    # Start a write
    processes[1].write(99, process_ids, lambda v: None)
    
    # Start two concurrent reads
    processes[2].read(process_ids, on_read_done("R1"))
    processes[3].read(process_ids, on_read_done("R2"))
    
    run_until_complete(net, processes)
    
    # The second read to complete should have timestamp >= first read's timestamp
    assert len(completion_order) == 2, "Both reads should have completed"
    
    first_pid = completion_order[0]
    second_pid = completion_order[1]
    
    first_ts = results[first_pid].timestamp
    second_ts = results[second_pid].timestamp
    
    assert second_ts >= first_ts, \
        f"Reads went backwards: first ts={first_ts}, second ts={second_ts}"
    print(f"Test 3 passed: Reads don't go backwards (first ts={first_ts}, second ts={second_ts})")


def test_concurrent_writes_result_in_consistent_reads():
    """
    Test 4: When multiple processes write concurrently, all reads after
    the writes complete must return the exact same value regardless of
    which process does the reading.
    """
    net = Network(latency=2)
    processes = [RegisterProcess(f"P{i}") for i in range(5)]
    process_ids = [f"P{i}" for i in range(5)]
    
    for p in processes:
        net.add_process(p)
    
    results = {}
    
    def on_read_done(pid):
        def callback(value):
            results[pid] = value
        return callback
    
    # Three concurrent writes with different values
    processes[0].write(100, process_ids, lambda v: None)
    processes[1].write(200, process_ids, lambda v: None)
    processes[2].write(300, process_ids, lambda v: None)
    
    run_until_complete(net, processes)
    
    # All 5 processes read
    for i in range(5):
        processes[i].read(process_ids, on_read_done(f"P{i}"))
    
    run_until_complete(net, processes)
    
    # All reads should return the same value
    values = [results[f"P{i}"].value for i in range(5)]
    timestamps = [results[f"P{i}"].timestamp for i in range(5)]
    
    assert len(set(values)) == 1, \
        f"Reads returned different values: {values}"
    assert len(set(str(ts) for ts in timestamps)) == 1, \
        f"Reads returned different timestamps: {timestamps}"
    
    # The value should be one of the written values
    assert values[0] in [100, 200, 300], \
        f"Read returned invented value {values[0]}"
    print(f"Test 4 passed: All reads returned consistent value {values[0]}")


def test_timestamp_tiebreak_by_writer_id():
    """
    Test 5: When two writers pick the same numeric timestamp,
    the tiebreak by writer ID is used consistently and all processes
    converge on the same winner.
    """
    net = Network(latency=2)
    processes = [RegisterProcess(f"P{i}") for i in range(5)]
    process_ids = [f"P{i}" for i in range(5)]
    
    for p in processes:
        net.add_process(p)
    
    results = {}
    
    def on_read_done(pid):
        def callback(value):
            results[pid] = value
        return callback
    
    # Three concurrent writes - they will all pick timestamp 1
    # but the winner should be determined by writer ID tiebreak
    processes[0].write(100, process_ids, lambda v: None)
    processes[1].write(200, process_ids, lambda v: None)
    processes[2].write(300, process_ids, lambda v: None)
    
    run_until_complete(net, processes)
    
    # All processes read
    for i in range(5):
        processes[i].read(process_ids, on_read_done(f"P{i}"))
    
    run_until_complete(net, processes)
    
    # All should have the same writer ID (the one that won the tiebreak)
    writer_ids = [results[f"P{i}"].timestamp.writer_id for i in range(5)]
    
    assert len(set(writer_ids)) == 1, \
        f"Processes have different writer IDs: {writer_ids}"
    
    # The winner should be one of P0, P1, P2
    assert writer_ids[0] in ["P0", "P1", "P2"], \
        f"Winner writer ID {writer_ids[0]} not from writing processes"
    
    # All processes should have the same value
    values = [results[f"P{i}"].value for i in range(5)]
    assert len(set(values)) == 1, \
        f"Processes have different values: {values}"
    
    print(f"Test 5 passed: All processes converged on writer {writer_ids[0]} with value {values[0]}")


def test_majority_survives_minority_crash():
    """
    Test 6: After crashing a minority of processes, the remaining
    majority should still be able to complete both reads and writes successfully.
    """
    net = Network(latency=2)
    processes = [RegisterProcess(f"P{i}") for i in range(5)]
    process_ids = [f"P{i}" for i in range(5)]
    
    for p in processes:
        net.add_process(p)
    
    results = {}
    
    def on_read_done(pid):
        def callback(value):
            results[pid] = value
        return callback
    
    # Initial write
    processes[0].write(42, process_ids, lambda v: None)
    run_until_complete(net, processes)
    
    # Crash minority (2 out of 5)
    processes[3].crash()
    processes[4].crash()
    
    alive_process_ids = ["P0", "P1", "P2"]
    
    # Write should still succeed with majority of remaining
    write_completed = [False]
    def on_write_done(v):
        write_completed[0] = True
    
    processes[0].write(99, alive_process_ids, on_write_done)
    run_until_complete(net, processes)
    
    assert write_completed[0], "Write should have completed with majority"
    
    # Read should also succeed
    processes[1].read(alive_process_ids, on_read_done("P1"))
    run_until_complete(net, processes)
    
    assert "P1" in results, "Read should have completed"
    assert results["P1"].value == 99, f"Expected 99, got {results['P1'].value}"
    
    print("Test 6 passed: Majority survives minority crash")


def test_crashed_process_does_not_affect_correctness():
    """
    Test 7: A crashed process must never affect the correctness
    of results returned to non-crashed processes.
    """
    net = Network(latency=2)
    processes = [RegisterProcess(f"P{i}") for i in range(5)]
    process_ids = [f"P{i}" for i in range(5)]
    
    for p in processes:
        net.add_process(p)
    
    results = {}
    written_values = set()
    
    def on_read_done(pid):
        def callback(value):
            results[pid] = value
        return callback
    
    # Write some values
    def on_write_done(value):
        written_values.add(value.value)
    
    processes[0].write(42, process_ids, on_write_done)
    run_until_complete(net, processes)
    
    processes[1].write(99, process_ids, on_write_done)
    run_until_complete(net, processes)
    
    # Crash one process
    processes[4].crash()
    
    # Continue with more writes
    processes[2].write(777, process_ids, on_write_done)
    run_until_complete(net, processes)
    
    # Read from remaining processes
    alive_ids = ["P0", "P1", "P2", "P3"]
    for pid in alive_ids:
        processes[int(pid[1:])].read(alive_ids, on_read_done(pid))
    
    run_until_complete(net, processes)
    
    # All reads should return valid values (either None or a written value)
    for pid, value in results.items():
        assert value.value is None or value.value in written_values, \
            f"{pid} returned invented value {value.value}"
    
    # All alive processes should have the same value
    values = [results[pid].value for pid in alive_ids]
    assert len(set(values)) == 1, \
        f"Alive processes have inconsistent values: {values}"
    
    print("Test 7 passed: Crashed process does not affect correctness")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Running Register Tests")
    print("=" * 60)
    print()
    
    test_non_concurrent_read_returns_last_written_value()
    test_concurrent_read_returns_only_old_or_new()
    test_atomic_reads_dont_go_backwards()
    test_concurrent_writes_result_in_consistent_reads()
    test_timestamp_tiebreak_by_writer_id()
    test_majority_survives_minority_crash()
    test_crashed_process_does_not_affect_correctness()
    
    print()
    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()