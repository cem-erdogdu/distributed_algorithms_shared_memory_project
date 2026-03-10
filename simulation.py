from network import Network
from process import Process


def build_network(num_processes, latency=1):
    net = Network(latency=latency)
    processes = [Process(i) for i in range(num_processes)]
    for p in processes:
        net.add_process(p)
    return net, processes


def run_simulation(net, ticks):
    for _ in range(ticks):
        net.step()
    return net.event_log


if __name__ == "__main__":
    net, processes = build_network(4)
    log = run_simulation(net, 10)
    print(f"Simulation complete. {len(log)} events recorded over 10 ticks.")
