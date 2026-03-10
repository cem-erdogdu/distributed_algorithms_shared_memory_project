import random


class Message:
    def __init__(self, sender, msg_type, payload=None):
        self.sender = sender
        self.msg_type = msg_type
        self.payload = payload or {}

    def __repr__(self):
        return f"Message(from={self.sender}, type={self.msg_type}, payload={self.payload})"


class Process:
    def __init__(self, proc_id):
        self.proc_id = proc_id
        self.network = None
        self.inbox = []
        self.crashed = False

    def connect(self, network):
        self.network = network

    def send(self, dest_id, msg_type, payload=None):
        if self.crashed:
            return
        self.network.deliver(self.proc_id, dest_id, msg_type, payload)

    def broadcast(self, msg_type, payload=None):
        if self.crashed:
            return
        for pid in self.network.processes:
            if pid != self.proc_id:
                self.send(pid, msg_type, payload)

    def on_message(self, message):
        pass

    def crash(self):
        self.crashed = True

    def tick(self, current_tick):
        pass
