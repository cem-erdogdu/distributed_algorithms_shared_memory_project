from process import Message


class Network:
    def __init__(self, latency=1):
        self.processes = {}
        self.latency = latency
        self.pending = []
        self.tick = 0
        self.event_log = []

    def add_process(self, process):
        self.processes[process.proc_id] = process
        process.connect(self)

    def deliver(self, sender_id, dest_id, msg_type, payload=None):
        deliver_at = self.tick + self.latency
        self.pending.append((deliver_at, sender_id, dest_id, msg_type, payload or {}))

    def step(self):
        self.tick += 1
        current = [e for e in self.pending if e[0] <= self.tick]
        self.pending = [e for e in self.pending if e[0] > self.tick]

        for (_, sender_id, dest_id, msg_type, payload) in current:
            dest = self.processes.get(dest_id)
            if dest and not dest.crashed:
                msg = Message(sender_id, msg_type, payload)
                self.event_log.append((self.tick, sender_id, dest_id, msg_type))
                dest.on_message(msg)

        for proc in self.processes.values():
            proc.tick(self.tick)

    def run(self, ticks):
        for _ in range(ticks):
            self.step()
