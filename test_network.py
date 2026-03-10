import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from network import Network
from process import Process, Message


class EchoProcess(Process):
    def __init__(self, proc_id):
        super().__init__(proc_id)
        self.received = []

    def on_message(self, message):
        self.received.append(message)


def test_message_delivery():
    net = Network(latency=1)
    p0 = EchoProcess(0)
    p1 = EchoProcess(1)
    net.add_process(p0)
    net.add_process(p1)

    p0.send(1, "ping", {"data": "hello"})
    net.step()

    assert len(p1.received) == 1
    assert p1.received[0].msg_type == "ping"
    assert p1.received[0].payload["data"] == "hello"


def test_crashed_process_does_not_receive():
    net = Network(latency=1)
    p0 = EchoProcess(0)
    p1 = EchoProcess(1)
    net.add_process(p0)
    net.add_process(p1)

    p1.crash()
    p0.send(1, "ping", {})
    net.step()

    assert len(p1.received) == 0


def test_broadcast_reaches_all():
    net = Network(latency=1)
    procs = [EchoProcess(i) for i in range(4)]
    for p in procs:
        net.add_process(p)

    procs[0].broadcast("hello", {})
    net.step()

    for p in procs[1:]:
        assert len(p.received) == 1


if __name__ == "__main__":
    test_message_delivery()
    test_crashed_process_does_not_receive()
    test_broadcast_reaches_all()
    print("All tests passed.")
