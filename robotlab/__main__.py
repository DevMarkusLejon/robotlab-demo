"""Run a deterministic demo, play interactively, or serve the local JSON API."""

import argparse
import json
from pathlib import Path

from .game import Board, choose_move
from .server import make_server
from .session import Session, make_command


def render_board(state):
    cells = [value or str(i) for i, value in enumerate(state["board"])]
    return "\n---------\n".join(" | ".join(cells[i:i + 3]) for i in range(0, 9, 3))


def play(interactive=False):
    session = Session()
    transcript = []
    print("RobotLab - SIMULATION ONLY. Remote player X, robot O. Cells 0-8.")
    while session.board.next_player:
        state = session.state()
        print("\n" + render_board(state))
        if state["next_player"] == "X":
            if interactive:
                try:
                    value = input("Your cell (q to quit): ").strip()
                except EOFError:
                    break
                if value.lower() == "q":
                    break
                try:
                    cell = int(value)
                    session.board.play(cell)
                except ValueError:
                    print("Choose an empty cell from 0 to 8.")
                    continue
            else:
                cell = choose_move(Board(tuple(state["board"])))
            command = make_command(state, "move", cell=cell)
        else:
            command = make_command(state, "robot_move")
        response = session.submit(command)
        transcript.append({"command": command, "response": response})
        result = response["result"]
        if result["status"] == "fault":
            print("Simulator fault; see transcript.")
            break
        print(f"{result['symbol']} -> cell {result['cell']} (simulated placement)")
    state = session.state()
    print("\n" + render_board(state))
    print("Draw." if state["is_draw"] else f"Winner: {state['winner'] or 'game unfinished'}")
    return {"simulation_only": True, "events": transcript, "final_state": state}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run optimal X and O through the simulator")
    demo.add_argument("--output", type=Path, help="Save a JSON trace")
    commands.add_parser("play", help="Play X against the simulated robot")
    serve = commands.add_parser("serve", help="Serve the loopback JSON API")
    serve.add_argument("--port", type=int, default=8765)
    webcam = commands.add_parser("webcam", help="Play X by pointing at cells through a webcam")
    webcam.add_argument("--camera", type=int, default=0, help="OpenCV camera index (default: 0)")
    webcam.add_argument("--stable-frames", type=int, default=12,
                        help="Frames a pointing position must remain stable (default: 12)")
    webcam.add_argument("--model", type=Path, help="Path to a MediaPipe .task model")
    commands.add_parser("download-model", help="Download the official MediaPipe hand model")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            with make_server(args.port) as server:
                print(f"SIMULATION ONLY: http://127.0.0.1:{server.server_port}/state", flush=True)
                server.serve_forever()
        elif args.command == "download-model":
            from .webcam import download_model
            print(download_model())
        elif args.command == "webcam":
            from .webcam import run_webcam
            kwargs = {"stable_frames": args.stable_frames}
            if args.model:
                kwargs["model_path"] = args.model
            result = run_webcam(args.camera, **kwargs)
            print(json.dumps(result["final_state"], ensure_ascii=False))
        else:
            trace = play(interactive=args.command == "play")
            if args.command == "demo" and args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(trace, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                print(f"Trace: {args.output}")
    except KeyboardInterrupt:
        print("\nSimulator closed.")


if __name__ == "__main__":
    main()
