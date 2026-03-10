from network import Network
from register import RegisterProcess, print_state_table
from rich.console import Console
from rich.panel import Panel

console = Console()


def run_stress_scenario():
    # Statistics tracking
    stats = {
        "total_writes": 0,
        "total_reads": 0,
        "quorum_sizes": [],
        "written_values": set(),
        "read_values": [],
    }

    # 7-process cluster with latency 2
    net = Network(latency=2)

    # Create 7 processes - all can read and write
    processes = [RegisterProcess(f"P{i}") for i in range(7)]
    process_ids = [f"P{i}" for i in range(7)]

    # Add all processes to network
    for p in processes:
        net.add_process(p)

    # Storage for results
    write_results = {}
    read_results = {}

    def on_write_done(pid):
        def callback(value):
            write_results[pid] = value
            stats["total_writes"] += 1
            stats["written_values"].add(value.value)
            participants = processes[int(pid[1:])].get_all_participants()
            stats["quorum_sizes"].append(len(participants))
            print_state_table(processes, completed_pid=pid, participants=participants,
                            tick=net.tick, operation_type=f"write by {pid}")
        return callback

    def on_read_done(pid):
        def callback(value):
            read_results[pid] = value
            stats["total_reads"] += 1
            stats["read_values"].append((pid, value.value, value.timestamp.writer_id))
            participants = processes[int(pid[1:])].get_all_participants()
            stats["quorum_sizes"].append(len(participants))
            print_state_table(processes, completed_pid=pid, participants=participants,
                            tick=net.tick, operation_type=f"read by {pid}")
        return callback

    console.print(Panel("[bold blue]STRESS TEST: Multi-Writer Atomic Register[/bold blue]", expand=False))
    console.print()

    # ===== PHASE 1: Three concurrent writes =====
    console.print(Panel("[bold yellow]Phase 1: Three concurrent writes[/bold yellow]", expand=False))
    console.print(f"Tick {net.tick}: P0, P1, P2 start writing concurrently with values 100, 200, 300")
    processes[0].write(100, process_ids, on_write_done("P0"))
    processes[1].write(200, process_ids, on_write_done("P1"))
    processes[2].write(300, process_ids, on_write_done("P2"))

    # ===== PHASE 2: Two concurrent reads while writes are in flight =====
    console.print(f"\nTick {net.tick}: P3, P4 start reading concurrently while writes are in flight")
    processes[3].read(process_ids, on_read_done("P3"))
    processes[4].read(process_ids, on_read_done("P4"))

    # Run until all writes and reads complete
    while any(p.is_busy() for p in processes):
        net.step()

    console.print(f"\nTick {net.tick}: All Phase 1 & 2 operations complete\n")

    # ===== PHASE 3: Crash two processes =====
    console.print(Panel("[bold red]Phase 3: Crash P5 and P6[/bold red]", expand=False))
    processes[5].crash()
    processes[6].crash()
    console.print(f"Tick {net.tick}: P5 and P6 have crashed!")
    print_state_table(processes, tick=net.tick)

    # Update process_ids to exclude crashed processes
    alive_process_ids = [f"P{i}" for i in range(5)]  # Only P0-P4 are alive

    # ===== PHASE 4: Concurrent writes from remaining processes =====
    console.print(Panel("[bold yellow]Phase 4: Concurrent writes from remaining processes[/bold yellow]", expand=False))
    console.print(f"Tick {net.tick}: P0, P2 start writing concurrently with values 500, 600")
    processes[0].write(500, alive_process_ids, on_write_done("P0"))
    processes[2].write(600, alive_process_ids, on_write_done("P2"))

    # ===== PHASE 5: Concurrent reads while writes in flight =====
    console.print(f"\nTick {net.tick}: P1, P3 start reading concurrently while writes are in flight")
    processes[1].read(alive_process_ids, on_read_done("P1"))
    processes[3].read(alive_process_ids, on_read_done("P3"))

    # Run until all operations complete
    while any(p.is_busy() for p in processes if not p.crashed):
        net.step()

    console.print(f"\nTick {net.tick}: All Phase 4 & 5 operations complete\n")

    # ===== PHASE 6: Final reads from all alive processes =====
    console.print(Panel("[bold yellow]Phase 6: Final reads from all alive processes[/bold yellow]", expand=False))
    console.print(f"Tick {net.tick}: P0, P1, P2, P3, P4 all read concurrently")
    for i in range(5):
        processes[i].read(alive_process_ids, on_read_done(f"P{i}"))

    # Run until all reads complete
    while any(p.is_busy() for p in processes if not p.crashed):
        net.step()

    console.print(f"\nTick {net.tick}: All final reads complete\n")

    # ===== SUMMARY =====
    console.print(Panel("[bold green]FINAL SUMMARY[/bold green]", expand=False))

    console.print(f"[bold]Total Operations:[/bold]")
    console.print(f"  Writes completed: {stats['total_writes']}")
    console.print(f"  Reads completed: {stats['total_reads']}")

    console.print(f"\n[bold]Quorum Participation:[/bold]")
    for i, size in enumerate(stats['quorum_sizes']):
        console.print(f"  Operation {i+1}: {size} processes in majority quorum")

    console.print(f"\n[bold]Values Written:[/bold] {sorted(stats['written_values'])}")

    console.print(f"\n[bold]Read Results Verification:[/bold]")
    all_valid = True
    for pid, value, writer_id in stats['read_values']:
        if value is None or value in stats['written_values']:
            status = "[green]VALID[/green]"
        else:
            status = "[red]INVALID - invented value![/red]"
            all_valid = False
        console.print(f"  {pid} read value {value} from writer {writer_id}: {status}")

    console.print()
    if all_valid:
        console.print(Panel("[bold green]VERIFICATION PASSED: All read values were actually written![/bold green]", expand=False))
    else:
        console.print(Panel("[bold red]VERIFICATION FAILED: Some read values were invented![/bold red]", expand=False))

    # Show final state
    console.print()
    print_state_table(processes, tick=net.tick)


if __name__ == "__main__":
    run_stress_scenario()
