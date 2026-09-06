import json
import unittest

from robotlab.server import make_server
from robotlab.session import CommandError, Session, make_command


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.clock_value = 1_000_000
        self.session = Session(clock=lambda: self.clock_value)

    def command(self, action="move", cell=0):
        kwargs = {"cell": cell} if action == "move" else {}
        return make_command(self.session.state(), action, clock=lambda: self.clock_value, **kwargs)

    def test_move_and_exact_retry_are_idempotent(self):
        command = self.command(cell=4)
        first = self.session.submit(command)
        retry = self.session.submit(command)
        self.assertFalse(first["duplicate"])
        self.assertTrue(retry["duplicate"])
        self.assertEqual(first["result"], retry["result"])
        self.assertEqual(self.session.state()["board"][4], "X")

    def test_revision_and_id_conflicts_do_not_mutate(self):
        command = self.command(cell=0)
        self.session.submit(command)
        stale = dict(command, command_id="other", cell=1)
        with self.assertRaises(CommandError) as ctx:
            self.session.submit(stale)
        self.assertEqual(ctx.exception.code, "revision_conflict")
        conflict = dict(command, cell=1)
        with self.assertRaises(CommandError) as ctx:
            self.session.submit(conflict)
        self.assertEqual(ctx.exception.code, "id_conflict")
        self.assertEqual(self.session.state()["board"].count("X"), 1)

    def test_expiry_and_deadline_are_rejected(self):
        expired = self.command(cell=0)
        expired["expires_at_ms"] = self.clock_value
        with self.assertRaises(CommandError) as ctx:
            self.session.submit(expired)
        self.assertEqual(ctx.exception.code, "expired")
        future = self.command(cell=0)
        future["expires_at_ms"] = self.clock_value + 30_001
        with self.assertRaises(CommandError) as ctx:
            self.session.submit(future)
        self.assertEqual(ctx.exception.code, "invalid_deadline")

    def test_stop_latches_and_reset_starts_new_session(self):
        stopped = self.session.submit(self.command("stop"))
        self.assertEqual(stopped["result"]["status"], "stopped")
        with self.assertRaises(CommandError) as ctx:
            self.session.submit(self.command(cell=0))
        self.assertEqual(ctx.exception.code, "stopped")
        old_id = self.session.session_id
        reset = self.session.submit(self.command("reset"))
        self.assertNotEqual(reset["state"]["session_id"], old_id)
        self.assertFalse(reset["state"]["stopped"])


class HttpTests(unittest.TestCase):
    def test_health_state_and_command_endpoint(self):
        import http.client
        server = make_server(0)
        try:
            import threading
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            conn.request("GET", "/health")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read())["simulation_only"])
            conn.request("GET", "/state")
            state = json.loads(conn.getresponse().read())
            from robotlab.session import make_command
            command = make_command(state, "move", cell=0)
            body = json.dumps(command, separators=(",", ":"))
            conn.request("POST", "/commands", body=body, headers={"Content-Type": "application/json"})
            reply = json.loads(conn.getresponse().read())
            self.assertEqual(reply["result"]["status"], "simulated")
            conn.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
